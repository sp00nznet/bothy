using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace Bothy.Desktop;

/// <summary>D3 — deployment monitor. A real top-level window, one per batch, so it
/// survives navigation in the main window and can be moved to a second display.</summary>
public partial class MonitorWindow : Window
{
    static readonly (string Name, string Status)[] DefaultJobs =
    {
        ("harbor", "complete"), ("gitea", "installing"), ("signoz", "queued"),
    };

    static readonly (string T, string Kind, string Text)[] DefaultLog =
    {
        ("22:01:03", "cmd", "pct create 129 local-lvm:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"),
        ("22:01:19", "detail", "  extracting rootfs ..."),
        ("22:01:44", "ok", "  container 129 created"),
        ("22:01:45", "cmd", "pct start 129"),
        ("22:02:02", "secret", "  resolving secret: GITEA_ADMIN_PASSWORD (vault: bothy/gitea)"),
        ("22:02:07", "detail", "  apt-get update && apt-get install -y git sqlite3"),
        ("22:02:11", "detail", "  systemd-networkd waiting for carrier ..."),
        ("22:02:15", "cmd", "systemctl enable --now gitea"),
        ("22:02:18", "ok", "  gitea listening on :3000"),
    };

    public MonitorWindow()
    {
        InitializeComponent();
        BuildTabs(DefaultJobs, activeIndex: 1);
        foreach (var (t, kind, text) in DefaultLog) AppendLog(t, kind, text);
    }

    void BuildTabs((string Name, string Status)[] jobs, int activeIndex)
    {
        Tabs.Children.Clear();
        for (int i = 0; i < jobs.Length; i++)
        {
            var (name, status) = jobs[i];
            bool active = i == activeIndex;
            var sp = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(11, 0, 11, 0) };
            sp.Children.Add(new System.Windows.Shapes.Ellipse
            {
                Width = 6, Height = 6, Fill = StatusBrush(status),
                VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 7, 0),
            });
            sp.Children.Add(new TextBlock
            {
                Text = name, FontSize = 11.5, VerticalAlignment = VerticalAlignment.Center,
                Foreground = active ? new SolidColorBrush(Color.FromRgb(0xDC, 0xDC, 0xDF))
                                    : new SolidColorBrush(Color.FromRgb(0x8A, 0x8A, 0x94)),
                FontWeight = active ? FontWeights.SemiBold : FontWeights.Normal,
            });
            Tabs.Children.Add(new Border
            {
                Child = sp, Height = 30,
                Background = active ? new SolidColorBrush(Color.FromRgb(0x20, 0x20, 0x24))
                                    : System.Windows.Media.Brushes.Transparent,
            });
        }
    }

    static SolidColorBrush StatusBrush(string status) => status switch
    {
        "complete" => new SolidColorBrush(Color.FromRgb(0x6C, 0xCB, 0x5F)),
        "installing" => new SolidColorBrush(Color.FromRgb(0x4C, 0xC2, 0xFF)),
        "failed" or "blocked" => new SolidColorBrush(Color.FromRgb(0xFF, 0x8A, 0x95)),
        _ => new SolidColorBrush(Color.FromRgb(0x7C, 0x7C, 0x86)),
    };

    public void AppendLog(string time, string kind, string text)
    {
        var line = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 2) };
        line.Children.Add(new TextBlock
        {
            Text = time, FontFamily = new FontFamily("Consolas"), FontSize = 11.5,
            Foreground = new SolidColorBrush(Color.FromRgb(0x5C, 0x5C, 0x66)),
            Margin = new Thickness(0, 0, 10, 0),
        });
        line.Children.Add(new TextBlock
        {
            Text = text, FontFamily = new FontFamily("Consolas"), FontSize = 11.5,
            Foreground = LogBrush(kind), TextWrapping = TextWrapping.Wrap, MaxWidth = 470,
        });
        LogBody.Children.Add(line);
    }

    static SolidColorBrush LogBrush(string kind) => kind switch
    {
        "ok" => new SolidColorBrush(Color.FromRgb(0x8F, 0xDC, 0x84)),
        "secret" => new SolidColorBrush(Color.FromRgb(0xE8, 0xC6, 0x5A)),
        "detail" => new SolidColorBrush(Color.FromRgb(0x7C, 0x7C, 0x86)),
        "error" => new SolidColorBrush(Color.FromRgb(0xFF, 0x8A, 0x95)),
        _ => new SolidColorBrush(Color.FromRgb(0xC9, 0xC9, 0xD1)),
    };

    void Close_Click(object sender, RoutedEventArgs e) => Close();
}
