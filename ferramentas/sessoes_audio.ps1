# Mostra os dispositivos padrão do Windows e quais programas estão usando cada
# dispositivo de áudio agora (só leitura). Útil para conferir se o Discord está
# ouvindo o CABLE Output e se nada além do Mic Limpo está tocando no CABLE Input.
#   powershell -ExecutionPolicy Bypass -File ferramentas\sessoes_audio.ps1

Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;

[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator {
  int EnumAudioEndpoints(int dataFlow, int stateMask, out IMMDeviceCollection devices);
  int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint);
}
[Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceCollection { int GetCount(out int n); int Item(int i, out IMMDevice d); }
[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice {
  int Activate(ref Guid iid, int clsCtx, IntPtr p, [MarshalAs(UnmanagedType.IUnknown)] out object i);
  int OpenPropertyStore(int access, out IPropertyStore store);
}
[Guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IPropertyStore { int GetCount(out int c); int GetAt(int i, out PK k); int GetValue(ref PK k, out PV v); }
[StructLayout(LayoutKind.Sequential)] struct PK { public Guid fmtid; public int pid; }
[StructLayout(LayoutKind.Explicit)] struct PV { [FieldOffset(0)] public short vt; [FieldOffset(8)] public IntPtr p; [FieldOffset(16)] public IntPtr p2; }
[Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioSessionManager2 {
  int GetAudioSessionControl(IntPtr g, int f, out IntPtr c);
  int GetSimpleAudioVolume(IntPtr g, int f, out IntPtr v);
  int GetSessionEnumerator(out IAudioSessionEnumerator e);
}
[Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioSessionEnumerator { int GetCount(out int n); int GetSession(int i, out IAudioSessionControl2 s); }
[Guid("bfb7ff88-7239-4fc9-8fa2-07c950be9c6d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioSessionControl2 {
  int GetState(out int s);
  int GetDisplayName(IntPtr n); int SetDisplayName(IntPtr n, IntPtr g);
  int GetIconPath(IntPtr p); int SetIconPath(IntPtr p, IntPtr g);
  int GetGroupingParam(out Guid g); int SetGroupingParam(IntPtr g, IntPtr c);
  int RegisterAudioSessionNotification(IntPtr n); int UnregisterAudioSessionNotification(IntPtr n);
  int GetSessionIdentifier(IntPtr s); int GetSessionInstanceIdentifier(IntPtr s);
  int GetProcessId(out int pid);
}
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumerator {}

public static class Audio {
  static string Nome(IMMDevice d) {
    IPropertyStore s; d.OpenPropertyStore(0, out s);
    var k = new PK { fmtid = new Guid("a45c254e-df1c-4efd-8020-67d146a850e0"), pid = 14 };
    PV v; s.GetValue(ref k, out v);
    return Marshal.PtrToStringUni(v.p);
  }
  public static string Padrao(int flow, int role) {
    var e = (IMMDeviceEnumerator)new MMDeviceEnumerator();
    IMMDevice d; return e.GetDefaultAudioEndpoint(flow, role, out d) == 0 ? Nome(d) : "(nenhum)";
  }
  public static List<string> Sessoes() {
    var r = new List<string>();
    var e = (IMMDeviceEnumerator)new MMDeviceEnumerator();
    var estados = new[] { "parada", "ATIVA", "encerrada" };
    for (int flow = 0; flow <= 1; flow++) {
      IMMDeviceCollection c; e.EnumAudioEndpoints(flow, 1, out c);
      int n; c.GetCount(out n);
      for (int i = 0; i < n; i++) {
        IMMDevice d; c.Item(i, out d);
        var iid = typeof(IAudioSessionManager2).GUID; object o;
        if (d.Activate(ref iid, 23, IntPtr.Zero, out o) != 0) continue;
        IAudioSessionEnumerator se; ((IAudioSessionManager2)o).GetSessionEnumerator(out se);
        int ns; se.GetCount(out ns);
        for (int j = 0; j < ns; j++) {
          IAudioSessionControl2 s; se.GetSession(j, out s);
          int st, pid; s.GetState(out st); s.GetProcessId(out pid);
          if (st == 2 || pid == 0) continue;
          string proc; try { proc = Process.GetProcessById(pid).ProcessName; } catch { proc = "?"; }
          r.Add(string.Format("{0,-7} {1,-45} {2,-18} {3}", flow == 0 ? "saída" : "entrada", Nome(d), proc, estados[st]));
        }
      }
    }
    return r;
  }
}
"@

"Saída padrão:  " + [Audio]::Padrao(0, 0) + "   (comunicações: " + [Audio]::Padrao(0, 2) + ")"
"Entrada padrão: " + [Audio]::Padrao(1, 0) + "   (comunicações: " + [Audio]::Padrao(1, 2) + ")"
""
"{0,-7} {1,-45} {2,-18} {3}" -f "tipo", "dispositivo", "programa", "sessão"
[Audio]::Sessoes() | Sort-Object
