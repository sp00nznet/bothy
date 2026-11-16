"""AWS EC2 adapter, verified against Amazon's local AWS Emulator.

Config (~/.bothy/config.toml):

    [[providers]]                      # real AWS
    name = "aws"
    type = "aws"
    node = "eu-west-1"                 # region
    user = "AKIA..."                   # access key id
    password = "..."                   # secret access key

    [[providers]]                      # the local emulator on port 9297
    name = "aws-emu"
    type = "aws"
    emulator = 9297

`emulator = <port>` reads the endpoint, CA and the keys the emulator generates
on start from ~/.aws/emulator/<port>/, so nothing secret is copied into Bothy.
The emulator records instance state but boots nothing: a deploy there proves
the API calls are right, not that the install script works.
"""
from __future__ import annotations

import configparser
import time
from pathlib import Path

from ..config import ProviderConfig
from ..estate import Service
from . import register
from .base import ProviderError, ProviderStatus

# smallest burstable size that fits (vcpus, memory MB)
_SIZES = [("t3.nano", 2, 512), ("t3.micro", 2, 1024), ("t3.small", 2, 2048),
          ("t3.medium", 2, 4096), ("t3.large", 2, 8192), ("t3.xlarge", 4, 16384),
          ("t3.2xlarge", 8, 32768)]
USERDATA_LIMIT = 16 * 1024          # EC2 rejects larger UserData


def instance_type(cores: int, memory_mb: int) -> str:
    for name, c, m in _SIZES:
        if c >= cores and m >= memory_mb:
            return name
    return _SIZES[-1][0]


def vmid_of(instance_id: str) -> int:
    """Estate rows key on an int; an EC2 id is hex after `i-`, so it maps 1:1."""
    return int(instance_id.split("-", 1)[1], 16)


class AwsProvider:
    def __init__(self, cfg: ProviderConfig):
        self.cfg = cfg
        self._session = None
        self._kw: dict = {}

    def _client(self, service: str):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as e:  # pragma: no cover
            raise ProviderError("boto3 is not installed (pip install boto3)") from e
        if self._session is None:
            extra = self.cfg.extra or {}
            region = self.cfg.node or "us-east-1"
            key, secret = self.cfg.user, self.cfg.password
            self._kw = {"config": Config(connect_timeout=5, read_timeout=30,
                                         retries={"max_attempts": 2})}
            port = extra.get("emulator")
            if port:
                d = Path.home() / ".aws" / "emulator" / str(port)
                creds = configparser.ConfigParser()
                if not creds.read(d / "emulator_credentials"):
                    raise ProviderError(f"no emulator credentials in {d} — is it running?")
                sec = creds[creds.sections()[0]]
                key, secret = sec["aws_access_key_id"], sec["aws_secret_access_key"]
                self._kw.update(endpoint_url=f"https://127.0.0.1:{port}", verify=str(d / "ca.pem"))
            elif self.cfg.host:                       # any other endpoint override
                self._kw.update(endpoint_url=self.cfg.host,
                                verify=extra.get("ca_bundle") or self.cfg.verify_ssl)
            self._session = boto3.Session(aws_access_key_id=key,
                                          aws_secret_access_key=secret,
                                          region_name=region)
        return self._session.client(service, **self._kw)

    def test(self) -> ProviderStatus:
        try:
            ident = self._client("sts").get_caller_identity()
            regions = self._client("ec2").describe_regions()["Regions"]
            region = self._session.region_name
            where = " (emulator)" if (self.cfg.extra or {}).get("emulator") else ""
            return ProviderStatus(ok=True, version=region, nodes=len(regions),
                                  detail=f"account {ident['Account']} · {region}{where}")
        except Exception as e:
            msg = str(e).split("\n")[0][:160]
            return ProviderStatus(ok=False, error=msg, detail=msg)

    def services(self) -> list[Service]:
        try:
            pages = self._client("ec2").get_paginator("describe_instances").paginate()
            insts = [i for p in pages for r in p["Reservations"] for i in r["Instances"]]
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"describe_instances: {e}") from e
        out = []
        for i in insts:
            state = i["State"]["Name"]
            if state == "terminated":
                continue
            tags = {t["Key"]: t["Value"] for t in i.get("Tags", [])}
            name = tags.get("Name") or i["InstanceId"]
            out.append(Service(
                vmid=vmid_of(i["InstanceId"]),
                hostname=name,
                address=i.get("PublicIpAddress") or i.get("PrivateIpAddress") or "",
                node=i.get("Placement", {}).get("AvailabilityZone", ""),
                provider="aws",
                status="running" if state == "running" else
                       "deploying" if state == "pending" else "stopped",
                mem_total_mb=next((m for n, _, m in _SIZES if n == i.get("InstanceType")), 1024),
                uptime="—",
                route="n/a",
                group=tags.get("bothy:group", "Unassigned"),
                definition_key=tags.get("bothy:key") or name.split("-")[0],
                kind="vm",
            ))
        return sorted(out, key=lambda s: s.vmid)


def pick_ami(ec2, prefer: str = "") -> str:
    """Newest Amazon Linux 2023 x86_64 image, unless the config names one."""
    if prefer:
        return prefer
    imgs = ec2.describe_images(Owners=["amazon"], Filters=[
        {"Name": "name", "Values": ["al2023-ami-2023*-x86_64"]},
        {"Name": "state", "Values": ["available"]}])["Images"]
    if not imgs:
        raise RuntimeError("no Amazon Linux 2023 image found — set ami = \"ami-...\"")
    return max(imgs, key=lambda i: i.get("CreationDate", ""))["ImageId"]


def build_run_params(job, ami: str, userdata: str) -> dict:
    """Exactly what RunInstances receives — the dry-run preview prints this too."""
    tags = [{"Key": "Name", "Value": job.hostname or job.key},
            {"Key": "bothy:key", "Value": job.key}]
    p = {"ImageId": ami, "InstanceType": instance_type(job.cores, job.memory_mb),
         "MinCount": 1, "MaxCount": 1,
         "BlockDeviceMappings": [{"DeviceName": "/dev/xvda",
                                  "Ebs": {"VolumeSize": max(8, job.disk_gb), "VolumeType": "gp3"}}],
         "TagSpecifications": [{"ResourceType": "instance", "Tags": tags}]}
    if userdata:
        p["UserData"] = userdata
    return p


def aws_dry_run(job) -> None:
    """Same parameters the real runner sends, printed instead of sent."""
    import json
    from ..install import render
    job.emit("detail", "DRY RUN — no changes will be made")
    ud = render(job.install_script, job.env) if job.install_script else ""
    p = build_run_params(job, job.template or "<newest al2023-ami x86_64>", ud)
    if ud:
        p["UserData"] = f"<{len(ud.splitlines())}-line install script, {len(ud.encode())} bytes>"
    job.pct, job.step = 50, "Launching instance"
    job.emit("cmd", "ec2 run-instances " + json.dumps(p))
    if len(ud.encode()) > USERDATA_LIMIT:
        job.emit("error", f"  a real run would refuse this: UserData over {USERDATA_LIMIT} bytes")
    job.pct = 95
    job.emit("ok", f"dry run complete for {job.name}")


def make_aws_runner(provider):
    """Real deploys. The install script becomes UserData: there is no node to
    SSH through, and SSM needs an agent an emulated instance never registers."""
    def run(job) -> None:
        from ..install import render
        ec2 = provider._client("ec2")
        job.pct, job.step = 5, "Selecting image"
        ami = pick_ami(ec2, (provider.cfg.extra or {}).get("ami", job.template or ""))
        job.emit("detail", f"image {ami}")

        userdata = render(job.install_script, job.env) if job.install_script else ""
        if len(userdata.encode()) > USERDATA_LIMIT:
            raise RuntimeError(f"install script is {len(userdata.encode())} bytes; "
                               f"EC2 UserData is capped at {USERDATA_LIMIT}")
        if userdata and job.secret_names:
            # ponytail: secrets ride in UserData, readable by anyone with
            # ec2:DescribeInstanceAttribute. Move to SSM Parameter Store if that matters.
            job.emit("secret", "  secrets are passed in UserData — visible to EC2 readers")

        job.pct, job.step = 30, "Launching instance"
        params = build_run_params(job, ami, userdata)
        job.emit("cmd", f"ec2 run-instances --image-id {ami} "
                        f"--instance-type {params['InstanceType']} --count 1")
        inst = ec2.run_instances(**params)["Instances"][0]
        iid = inst["InstanceId"]
        job.vmid = vmid_of(iid)
        job.target = f"{provider._session.region_name} · {iid}"

        job.pct, job.step = 70, "Waiting for running"
        ec2.get_waiter("instance_running").wait(
            InstanceIds=[iid], WaiterConfig={"Delay": 5, "MaxAttempts": 120})
        job.emit("ok", f"instance {iid} running")
        if userdata:
            job.emit("detail", "install script handed to cloud-init; its output is in "
                               "/var/log/cloud-init-output.log on the instance")
        job.pct, job.step = 100, "Instance running"
    return run


register("aws", AwsProvider)
