using System;
using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace Bothy.Desktop;

public partial class App : Application
{
    public static string? ShotPath;
    public static string Screen = "main";      // main | deploy | monitor | provider | tray

    protected override void OnStartup(StartupEventArgs e)
    {
        for (int i = 0; i < e.Args.Length - 1; i++)
        {
            if (e.Args[i] == "--shot") ShotPath = e.Args[i + 1];
            if (e.Args[i] == "--screen") Screen = e.Args[i + 1];
        }
        base.OnStartup(e);

        // secondary screens are their own top-level windows, shot directly
        Window? w = Screen switch
        {
            "deploy" => new DeployDialog(),
            "monitor" => new MonitorWindow(),
            "provider" => new ProviderPropertiesWindow(),
            "tray" => new TrayWindow(),
            _ => null,
        };
        if (w is null)
        {
            new MainWindow().Show();          // StartupUri removed; show explicitly
            return;
        }
        w.Show();
        if (ShotPath is { } shot)
            w.Dispatcher.BeginInvoke(System.Windows.Threading.DispatcherPriority.ContextIdle,
                new Action(() => { Capture(w, shot); Shutdown(); }));
    }

    /// <summary>Render the live visual tree to PNG.
    /// Screen capture (Graphics.CopyFromScreen) returns blank for DWM-composited
    /// WPF windows, so the app renders itself instead.</summary>
    public static void Capture(FrameworkElement root, string path, double scale = 2.0)
    {
        root.UpdateLayout();
        int w = (int)Math.Ceiling(root.ActualWidth * scale);
        int h = (int)Math.Ceiling(root.ActualHeight * scale);
        var rtb = new RenderTargetBitmap(w, h, 96 * scale, 96 * scale, PixelFormats.Pbgra32);
        rtb.Render(root);
        var enc = new PngBitmapEncoder();
        enc.Frames.Add(BitmapFrame.Create(rtb));
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        using var fs = File.Create(path);
        enc.Save(fs);
    }
}
