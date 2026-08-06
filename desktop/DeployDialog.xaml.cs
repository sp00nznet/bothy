using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace Bothy.Desktop;

/// <summary>D2 — deploy wizard. NumberBox-style fields with spinners, per the design.</summary>
public partial class DeployDialog : Window
{
    public DeployDialog(string appName = "Gitea", string node = "pve01",
                        int cores = 2, int memoryMb = 2048, int diskGb = 30)
    {
        InitializeComponent();
        DlgTitle.Text = $"Deploy {appName} — Resources";
        FitText.Text = $"✓ Fits {node} — 38% headroom remains";
        BuildFields(cores, memoryMb, diskGb, appName.ToLowerInvariant());
    }

    /// <summary>label (104) | field (1*) | hint (96), right-aligned labels.</summary>
    void BuildFields(int cores, int memoryMb, int diskGb, string hostname)
    {
        var rows = new (string Label, string Value, string Hint, bool Spinner)[]
        {
            ("vCPU", cores.ToString(), "of 16 free", true),
            ("Memory (MB)", memoryMb.ToString(), "of 46 GB free", true),
            ("Disk (GB)", diskGb.ToString(), "of 4.1 TB free", true),
            ("Storage", "local-lvm", "4.1 TB free", false),
            ("Hostname", hostname, "", false),
        };

        FieldGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(104) });
        FieldGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        FieldGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(96) });

        int r = 0;
        foreach (var (label, value, hint, spinner) in rows)
        {
            FieldGrid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(36) });

            var lb = new TextBlock
            {
                Text = label, FontSize = 12, Foreground = Brush(0x8A, 0x8A, 0x94),
                HorizontalAlignment = HorizontalAlignment.Right,
                VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 10, 0),
            };
            Grid.SetRow(lb, r); Grid.SetColumn(lb, 0);
            FieldGrid.Children.Add(lb);

            // focused field gets an accent border plus a 1px accent underline (Fluent focus)
            bool focused = r == 0;
            var field = new Border
            {
                Background = Brush(0x1A, 0x1A, 0x1E),
                BorderBrush = focused ? Brush(0x4C, 0xC2, 0xFF) : Brush(0x2A, 0x2A, 0x30),
                BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(4),
                Height = 28, VerticalAlignment = VerticalAlignment.Center,
            };
            var inner = new DockPanel { LastChildFill = true };
            if (spinner)
            {
                var spin = new StackPanel { Orientation = Orientation.Vertical, Width = 18,
                                            VerticalAlignment = VerticalAlignment.Center };
                spin.Children.Add(Glyph("", 7));   // up
                spin.Children.Add(Glyph("", 7));   // down
                DockPanel.SetDock(spin, Dock.Right);
                inner.Children.Add(spin);
            }
            inner.Children.Add(new TextBlock
            {
                Text = value, FontFamily = new FontFamily("Consolas"), FontSize = 12,
                Foreground = Brush(0xDC, 0xDC, 0xDF), VerticalAlignment = VerticalAlignment.Center,
                Margin = new Thickness(9, 0, 0, 0),
            });
            field.Child = inner;

            var wrap = new StackPanel();
            wrap.Children.Add(field);
            if (focused)
                wrap.Children.Add(new Border { Height = 1, Background = Brush(0x4C, 0xC2, 0xFF),
                                               Margin = new Thickness(1, -1, 1, 0) });
            Grid.SetRow(wrap, r); Grid.SetColumn(wrap, 1);
            FieldGrid.Children.Add(wrap);

            if (hint.Length > 0)
            {
                var ht = new TextBlock
                {
                    Text = hint, FontSize = 11, Foreground = Brush(0x7C, 0x7C, 0x86),
                    VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(10, 0, 0, 0),
                };
                Grid.SetRow(ht, r); Grid.SetColumn(ht, 2);
                FieldGrid.Children.Add(ht);
            }
            r++;
        }
    }

    static TextBlock Glyph(string g, double size) => new()
    {
        Text = g, FontFamily = new FontFamily("Segoe Fluent Icons,Segoe MDL2 Assets"),
        FontSize = size, Foreground = Brush(0x8A, 0x8A, 0x94),
        HorizontalAlignment = HorizontalAlignment.Center,
    };

    static SolidColorBrush Brush(byte r, byte g, byte b) =>
        new(Color.FromRgb(r, g, b));

    void Cancel_Click(object sender, RoutedEventArgs e) => Close();
    void Next_Click(object sender, RoutedEventArgs e) => Close();
}
