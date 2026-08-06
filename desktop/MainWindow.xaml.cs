using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace Bothy.Desktop;

public class Guest
{
    public int Vmid { get; init; }
    public string Hostname { get; init; } = "";
    public string Address { get; init; } = "";
    public string Cpu { get; init; } = "";
    public string Memory { get; init; } = "";
    public string Uptime { get; init; } = "";
    public string Route { get; init; } = "";
    public string Status { get; init; } = "running";
    public string Group { get; init; } = "Unassigned";

    public Brush StatusBrush => Status switch
    {
        "degraded" => new SolidColorBrush(Color.FromRgb(0xF2, 0xC7, 0x44)),
        "deploying" => new SolidColorBrush(Color.FromRgb(0x4C, 0xC2, 0xFF)),
        "stopped" => new SolidColorBrush(Color.FromRgb(0x7C, 0x7C, 0x86)),
        _ => new SolidColorBrush(Color.FromRgb(0x6C, 0xCB, 0x5F)),
    };

    public Brush RouteBrush => Route switch
    {
        var r when r.StartsWith("2") => new SolidColorBrush(Color.FromRgb(0x8F, 0xDC, 0x84)),
        "deploying" => new SolidColorBrush(Color.FromRgb(0x4C, 0xC2, 0xFF)),
        "direct" or "n/a" => new SolidColorBrush(Color.FromRgb(0x8A, 0x8A, 0x94)),
        _ => new SolidColorBrush(Color.FromRgb(0xFF, 0x8A, 0x95)),
    };
}

public partial class MainWindow : Window
{
    public ObservableCollection<Guest> Guests { get; } = new();
    int CatalogCount, QueueCount;      // filled from the API, 0 until then

    /// <summary>Where the Flask console is serving. Same API the web console uses.</summary>
    public static string ApiBase =
        Environment.GetEnvironmentVariable("BOTHY_API") ?? "http://127.0.0.1:8760";

    public MainWindow()
    {
        InitializeComponent();
        LoadSample();                       // shown only until the API answers
        List.ItemsSource = Guests;
        BuildTree();
        List.SelectedIndex = 0;
        List.SelectionChanged += (_, _) => UpdateDetails();
        UpdateDetails();

        _ = LoadFromApiAsync();

        // F5 refresh, Ctrl+M monitor, Ctrl+B batch, Del destroy - per the design
        KeyDown += (_, ev) =>
        {
            bool ctrl = (System.Windows.Input.Keyboard.Modifiers &
                         System.Windows.Input.ModifierKeys.Control) != 0;
            if (ev.Key == System.Windows.Input.Key.F5) _ = LoadFromApiAsync();
            else if (ctrl && ev.Key == System.Windows.Input.Key.M) Monitor_Click(this, new RoutedEventArgs());
            else if (ctrl && ev.Key == System.Windows.Input.Key.B) Deploy_Click(this, new RoutedEventArgs());
        };

        if (App.ShotPath is { } shot)
        {
            // render after the first layout+render pass has completed
            Loaded += (_, _) => Dispatcher.BeginInvoke(
                System.Windows.Threading.DispatcherPriority.ContextIdle,
                new Action(() => { App.Capture(this, shot); Application.Current.Shutdown(); }));
        }
    }

    /// <summary>Replace the placeholder list with the live estate.
    /// A failure leaves the placeholder in place and says so in the status bar,
    /// rather than blanking the window.</summary>
    async Task LoadFromApiAsync()
    {
        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(20) };
            var json = await http.GetStringAsync($"{ApiBase}/api/estate");
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            var list = new List<Guest>();
            foreach (var s in root.GetProperty("services").EnumerateArray())
            {
                string Str(string n) => s.TryGetProperty(n, out var v) ? (v.GetString() ?? "") : "";
                list.Add(new Guest
                {
                    Vmid = s.GetProperty("vmid").GetInt32(),
                    Hostname = Str("hostname"),
                    Address = Str("address"),
                    Cpu = s.GetProperty("cpu_pct").GetInt32() + "%",
                    Memory = Str("mem_label"),
                    Uptime = Str("uptime"),
                    Route = Str("route"),
                    Status = Str("status"),
                    Group = Str("node"),
                });
            }
            if (list.Count == 0) return;
            Guests.Clear();
            foreach (var g in list.OrderBy(g => g.Vmid)) Guests.Add(g);
            // Fetch the counts BEFORE building the tree: BuildTree reads these
            // fields, so filling them afterwards left "Catalog 0" on screen
            // however many definitions the server actually had.
            try
            {
                var cj = await http.GetStringAsync($"{ApiBase}/api/catalog?q=__none__");
                using var cd = JsonDocument.Parse(cj);
                CatalogCount = cd.RootElement.GetProperty("total").GetInt32();
                var qj = await http.GetStringAsync($"{ApiBase}/api/queue");
                using var qd = JsonDocument.Parse(qj);
                QueueCount = qd.RootElement.TryGetProperty("total", out var t) ? t.GetInt32() : 0;
            }
            catch { /* counts are cosmetic; the estate already loaded */ }
            Tree.Items.Clear();
            BuildTree();
            List.SelectedIndex = 0;
            UpdateDetails();
            var counts = root.GetProperty("counts");
            StatusLeft.Text = $"{counts.GetProperty("total").GetInt32()} services · 1 selected";
            StatusMid.Text = $"live · {root.GetProperty("capacity_pct").GetInt32()}% capacity";
        }
        catch (Exception e)
        {
            StatusMid.Text = $"API unreachable ({e.GetType().Name}) — showing placeholder data";
            StatusMid.Foreground = new SolidColorBrush(Color.FromRgb(0xF2, 0xC7, 0x44));
        }
    }

    void LoadSample()
    {
        var rows = new (int, string, string, string, string, string, string, string, string)[]
        {
            (100, "plex", "203.0.113.100", "12%", "2.3/4G", "14d 6h", "200 OK", "running", "Media"),
            (101, "sonarr", "203.0.113.101", "4%", "700M/2G", "14d 6h", "200 OK", "running", "Media"),
            (102, "radarr", "203.0.113.102", "5%", "760M/2G", "9d 2h", "200 OK", "running", "Media"),
            (103, "sabnzbd", "203.0.113.103", "21%", "1.1/2G", "9d 2h", "200 OK", "running", "Media"),
            (104, "jellyfin", "203.0.113.104", "63%", "3.5/4G", "2d 4h", "502", "degraded", "Media"),
            (110, "gitea", "203.0.113.110", "8%", "1.5/4G", "31d 1h", "200 OK", "running", "DevOps"),
            (111, "drone", "203.0.113.111", "3%", "600M/2G", "31d 1h", "direct", "running", "DevOps"),
            (112, "harbor", "203.0.113.112", "17%", "2.8/4G", "6d 8h", "200 OK", "running", "DevOps"),
            (113, "registry", "203.0.113.113", "2%", "380M/1G", "6d 8h", "direct", "running", "DevOps"),
            (120, "gitea-new", "203.0.113.120", "0%", "0M/4G", "—", "deploying", "deploying", "DevOps"),
            (130, "traefik", "203.0.113.130", "6%", "420M/1G", "44d 3h", "200 OK", "running", "Infrastructure"),
            (131, "pihole", "203.0.113.131", "3%", "300M/1G", "44d 3h", "200 OK", "running", "Infrastructure"),
            (132, "vaultwarden", "203.0.113.132", "2%", "260M/1G", "21d 7h", "timeout", "running", "Infrastructure"),
            (133, "uptime-kuma", "203.0.113.133", "4%", "410M/1G", "21d 7h", "200 OK", "running", "Infrastructure"),
            (140, "nextcloud", "203.0.113.140", "19%", "3.0/6G", "12d 5h", "200 OK", "running", "Unassigned"),
        };
        foreach (var (v, h, a, c, m, u, r, s, g) in rows)
            Guests.Add(new Guest { Vmid = v, Hostname = h, Address = a, Cpu = c, Memory = m,
                                   Uptime = u, Route = r, Status = s, Group = g });
    }

    static TreeViewItem Node(string label, int? count, Brush? square = null, bool expanded = true)
    {
        var sp = new StackPanel { Orientation = Orientation.Horizontal, Height = 26 };
        if (square is not null)
            sp.Children.Add(new System.Windows.Shapes.Rectangle
            {
                Width = 12, Height = 12, Fill = square, RadiusX = 2, RadiusY = 2,
                VerticalAlignment = VerticalAlignment.Center,
                Margin = new Thickness(0, 0, 8, 0)
            });
        sp.Children.Add(new TextBlock { Text = label, VerticalAlignment = VerticalAlignment.Center });
        if (count is not null)
            sp.Children.Add(new TextBlock
            {
                Text = count.ToString(), FontFamily = new FontFamily("Consolas"), FontSize = 11,
                Foreground = new SolidColorBrush(Color.FromRgb(0x7C, 0x7C, 0x86)),
                VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(10, 0, 0, 0)
            });
        return new TreeViewItem { Header = sp, IsExpanded = expanded };
    }

    void BuildTree()
    {
        var prox = new SolidColorBrush(Color.FromArgb(0x59, 0xE5, 0x70, 0x00));

        // Only nodes actually present in the estate are shown. Listing providers
        // that are not configured would be inventing infrastructure.
        var estate = Node("Estate", Guests.Count);
        var pool = Node("Proxmox", Guests.Count, prox);
        foreach (var nodeName in Guests.Select(x => x.Group).Distinct().OrderBy(x => x))
        {
            int n = Guests.Count(x => x.Group == nodeName);
            int running = Guests.Count(x => x.Group == nodeName && x.Status == "running");
            var tn = Node(nodeName, n, prox, false);
            if (running > 0)
                tn.Items.Add(Node($"running", running,
                    new SolidColorBrush(Color.FromRgb(0x6C, 0xCB, 0x5F)), false));
            pool.Items.Add(tn);
        }
        estate.Items.Add(pool);

        var catalog = Node("Catalog", CatalogCount, null, false);
        var queue = Node("Queue", QueueCount, null, false);

        Tree.Items.Add(estate);
        Tree.Items.Add(catalog);
        Tree.Items.Add(queue);
    }

    static void Fill(Grid grid, IEnumerable<(string, string)> rows)
    {
        grid.Children.Clear();
        grid.RowDefinitions.Clear();
        grid.ColumnDefinitions.Clear();
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(96) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        int r = 0;
        foreach (var (k, v) in rows)
        {
            grid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(22) });
            var kt = new TextBlock { Text = k, FontSize = 11.5,
                Foreground = new SolidColorBrush(Color.FromRgb(0x8A, 0x8A, 0x94)) };
            var vt = new TextBlock { Text = v, FontSize = 11.5, FontFamily = new FontFamily("Consolas"),
                Foreground = new SolidColorBrush(Color.FromRgb(0xDC, 0xDC, 0xDF)) };
            Grid.SetRow(kt, r); Grid.SetColumn(kt, 0);
            Grid.SetRow(vt, r); Grid.SetColumn(vt, 1);
            grid.Children.Add(kt); grid.Children.Add(vt);
            r++;
        }
    }

    void Deploy_Click(object sender, RoutedEventArgs e)
    {
        var g = List.SelectedItem as Guest;
        new DeployDialog(g?.Hostname ?? "Gitea", g?.Group ?? "pve01") { Owner = this }.ShowDialog();
    }

    // one monitor per batch, non-modal, outliving navigation in the main window
    static MonitorWindow? _monitor;
    void Monitor_Click(object sender, RoutedEventArgs e)
    {
        if (_monitor is null || !_monitor.IsLoaded)
        {
            _monitor = new MonitorWindow();
            _monitor.Closed += (_, _) => _monitor = null;
        }
        _monitor.Show();
        _monitor.Activate();
    }

    void Provider_Click(object sender, RoutedEventArgs e) =>
        new ProviderPropertiesWindow { Owner = this }.ShowDialog();

    void UpdateDetails()
    {
        if (List.SelectedItem is not Guest g) return;
        DetailName.Text = g.Hostname;
        DetailSub.Text = $"LXC {g.Vmid} · {g.Status} {g.Uptime}";
        Fill(IdentityGrid, new (string, string)[]
        {
            ("VMID", g.Vmid.ToString()), ("Address", g.Address == "" ? "—" : g.Address),
            ("Node", g.Group), ("Status", g.Status),
        });
        Fill(ResourcesGrid, new (string, string)[]
        {
            ("CPU", g.Cpu), ("Memory", g.Memory),
        });
        Fill(HealthGrid, new (string, string)[]
        {
            ("Route", g.Route), ("Uptime", g.Uptime), ("Audited", "4 min ago"),
        });
    }
}
