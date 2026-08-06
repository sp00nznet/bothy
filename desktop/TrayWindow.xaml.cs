using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace Bothy.Desktop;

/// <summary>D5 — tray menu and completion toast.</summary>
public partial class TrayWindow : Window
{
    public TrayWindow()
    {
        InitializeComponent();
        BuildMenu();
    }

    void BuildMenu()
    {
        // (label, shortcut, isSeparatorAfter, isChecked)
        var items = new (string Label, string Key, bool SepAfter, bool Checked)[]
        {
            ("Open Bothy", "", false, false),
            ("Deployment monitor", "Ctrl+M", true, false),
            ("Deploy from collection", "", false, false),
            ("Refresh estate", "F5", true, false),
            ("Home lab (pve01)", "", true, true),
            ("Exit", "", false, false),
        };

        foreach (var (label, key, sepAfter, chk) in items)
        {
            var dock = new DockPanel { Height = 28, LastChildFill = false };
            var text = new TextBlock
            {
                Text = label, FontSize = 11.5, VerticalAlignment = VerticalAlignment.Center,
                Margin = new Thickness(12, 0, 0, 0),
                Foreground = new SolidColorBrush(Color.FromRgb(0xDC, 0xDC, 0xDF)),
            };
            DockPanel.SetDock(text, Dock.Left);
            dock.Children.Add(text);

            if (chk)
            {
                var tick = new TextBlock
                {
                    Text = "✓", FontSize = 11, Margin = new Thickness(8, 0, 12, 0),
                    VerticalAlignment = VerticalAlignment.Center,
                    Foreground = new SolidColorBrush(Color.FromRgb(0x6C, 0xCB, 0x5F)),
                };
                DockPanel.SetDock(tick, Dock.Right);
                dock.Children.Add(tick);
            }
            if (key.Length > 0)
            {
                var k = new TextBlock
                {
                    Text = key, FontFamily = new FontFamily("Consolas"), FontSize = 10.5,
                    VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 12, 0),
                    Foreground = new SolidColorBrush(Color.FromRgb(0x7C, 0x7C, 0x86)),
                };
                DockPanel.SetDock(k, Dock.Right);
                dock.Children.Add(k);
            }
            TrayMenu.Children.Add(dock);

            if (sepAfter)
                TrayMenu.Children.Add(new Border
                {
                    Height = 1, Margin = new Thickness(8, 4, 8, 4),
                    Background = new SolidColorBrush(Color.FromArgb(0x22, 0xFF, 0xFF, 0xFF)),
                });
        }
    }
}
