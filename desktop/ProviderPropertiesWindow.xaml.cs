using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace Bothy.Desktop;

/// <summary>D4 — provider property sheet. 110px right-aligned labels; the rows that
/// reference something on disk or in a vault carry a trailing browse button, because
/// typing a key path from memory is how people get it wrong.</summary>
public partial class ProviderPropertiesWindow : Window
{
    public ProviderPropertiesWindow()
    {
        InitializeComponent();
        BuildFields();
    }

    void BuildFields()
    {
        var rows = new (string Label, string Value, string Trailing, bool Mono)[]
        {
            ("Display name", "Home lab", "", false),
            ("Host", "pve01.example.com", "", true),
            ("Port", "8006", "", true),
            ("User", "root@pam", "", true),
            ("Token secret", "••• (vault: pve-token)", "Vault…", true),
            ("SSH key", @"C:\Users\you\.ssh\id_ed25519", "Browse…", true),
        };

        FieldGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(110) });
        FieldGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

        int r = 0;
        foreach (var (label, value, trailing, mono) in rows)
        {
            FieldGrid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(34) });

            var lb = new TextBlock
            {
                Text = label, FontSize = 12, Foreground = B(0x8A, 0x8A, 0x94),
                HorizontalAlignment = HorizontalAlignment.Right,
                VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 10, 0),
            };
            Grid.SetRow(lb, r); Grid.SetColumn(lb, 0);
            FieldGrid.Children.Add(lb);

            var dock = new DockPanel { LastChildFill = true, VerticalAlignment = VerticalAlignment.Center };
            if (trailing.Length > 0)
            {
                var btn = new Button
                {
                    Content = new TextBlock { Text = trailing, FontSize = 11.5 },
                    Style = (Style)FindResource("CmdButton"),
                    Height = 28, Width = 72, Margin = new Thickness(8, 0, 0, 0),
                    BorderBrush = B(0x2A, 0x2A, 0x30), BorderThickness = new Thickness(1),
                };
                DockPanel.SetDock(btn, Dock.Right);
                dock.Children.Add(btn);
            }
            dock.Children.Add(new Border
            {
                Background = B(0x1A, 0x1A, 0x1E), BorderBrush = B(0x2A, 0x2A, 0x30),
                BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(4), Height = 28,
                Child = new TextBlock
                {
                    Text = value, FontSize = 12, Foreground = B(0xDC, 0xDC, 0xDF),
                    FontFamily = mono ? new FontFamily("Consolas") : new FontFamily("Segoe UI"),
                    VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(9, 0, 0, 0),
                    TextTrimming = TextTrimming.CharacterEllipsis,
                },
            });
            Grid.SetRow(dock, r); Grid.SetColumn(dock, 1);
            FieldGrid.Children.Add(dock);
            r++;
        }
    }

    static SolidColorBrush B(byte r, byte g, byte b) => new(Color.FromRgb(r, g, b));

    void Close_Click(object sender, RoutedEventArgs e) => Close();
}
