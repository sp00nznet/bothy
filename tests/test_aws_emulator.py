"""AWS adapter against Amazon's local AWS Emulator. `python tests/test_aws_emulator.py`

Start the emulator first (docs/aws-emulator.md); skips if it is not running.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bothy.config import ProviderConfig
from bothy.deploy import DeployJob
from bothy.providers import build
from bothy.providers.aws import make_aws_runner, vmid_of

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9297


def main() -> int:
    if not (Path.home() / ".aws" / "emulator" / str(PORT) / "emulator_credentials").exists():
        print(f"SKIP: no emulator on {PORT}")
        return 0
    cfg = ProviderConfig(name="emu", type="aws", extra={"emulator": PORT})
    assert cfg.configured
    p = build(cfg)
    st = p.test()
    assert st.ok and "000000000000" in st.detail, st
    before = {s.vmid for s in p.services()}

    lines = []
    job = DeployJob(key="gitea", name="Gitea", cores=2, memory_mb=2048, disk_gb=20,
                    hostname="gitea-emu", install_script="#!/bin/bash\necho hello",
                    env={"ADMIN_PASS": "a b'$c"}, secret_names=["ADMIN_PASS"])
    job.emit = lambda kind, text: lines.append((kind, text))
    make_aws_runner(p)(job)
    assert job.pct == 100 and job.vmid, job

    after = {s.vmid: s for s in p.services()}
    new = after[job.vmid]
    assert job.vmid not in before
    assert new.hostname == "gitea-emu" and new.status == "running" and new.provider == "aws"
    assert new.definition_key == "gitea" and new.address, new
    assert any(k == "secret" for k, _ in lines), "UserData secret warning missing"

    # UserData must carry the rendered (quoted) script, exactly once encoded
    import base64
    iid = job.target.split(" · ")[1]
    assert vmid_of(iid) == job.vmid
    ud = p._client("ec2").describe_instance_attribute(InstanceId=iid, Attribute="userData")
    text = base64.b64decode(ud["UserData"]["Value"]).decode()
    assert "echo hello" in text and "export ADMIN_PASS='a b'\"'\"'$c'" in text, text
    p._client("ec2").terminate_instances(InstanceIds=[iid])
    print(f"ok: test, services, deploy {iid}, UserData round-trip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
