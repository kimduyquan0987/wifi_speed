#!/usr/bin/env python3
"""
wifi_speed.py

Cross-platform small GUI tool to read Wi‑Fi link rate (adapter reported) and perform an Internet speed test
(download/upload/ping) using speedtest-cli.

Requirements:
  - Python 3.7+
  - pip install speedtest-cli

Usage:
  python wifi_speed.py

This is a single-file Tkinter app. It attempts to detect the platform and use native commands
to read the Wi‑Fi link rate (Windows: netsh; Linux: iwconfig/iw; macOS: airport).
It also runs a Speedtest.net test via the speedtest module.
"""

import sys
import platform
import subprocess
import re
import threading
import time
from datetime import datetime
import json, shutil, subprocess
# FORCE include speedtest for PyInstaller
try:
    # import the package with a deterministic name so PyInstaller picks it up
    import speedtest  # noqa: F401
except Exception:
    # ignore at runtime if not available; build-time import helps PyInstaller
    pass


try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
except Exception:
    raise SystemExit('Tkinter is required (standard with CPython).')

APP_TITLE = 'Wi‑Fi Speed Reader'
LOG_FILE_DEFAULT = 'wifi_speed_log.txt'

# ----------------------------- Link speed helpers -----------------------------
def run_cmd(cmd):
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=6)
        return proc.stdout + proc.stderr
    except Exception as e:
        return ''

def parse_windows_netsh(output):
    # Look for "Receive rate (Mbps)" or "Transmit rate (Mbps)"
    m = re.search(r'Receive rate \\(Mbps\\)\\s*:\\s*([\\d\\.]+)', output, re.IGNORECASE)
    if m:
        return float(m.group(1))
    m2 = re.search(r'Transmit rate \\(Mbps\\)\\s*:\\s*([\\d\\.]+)', output, re.IGNORECASE)
    if m2:
        return float(m2.group(1))
    # fallback: search numbers with Mbps
    m3 = re.search(r'([\\d\\.]+)\\s*Mbps', output, re.IGNORECASE)
    if m3:
        return float(m3.group(1))
    return None

def get_windows_link_speed():
    out = run_cmd('netsh wlan show interfaces')
    return parse_windows_netsh(out)

def parse_linux_iwconfig(output):
    # iwconfig: contains "Bit Rate=54 Mb/s"
    m = re.search(r'Bit Rate[:=]\\s*([\\d\\.]+)\\s*Mb', output, re.IGNORECASE)
    if m:
        return float(m.group(1))
    # iw dev wlan0 link: "tx bitrate: 144.4 MBit/s"
    m2 = re.search(r'(tx|rx) bitrate[:=]?\\s*([\\d\\.]+)\\s*M', output, re.IGNORECASE)
    if m2:
        return float(m2.group(2))
    return None

def get_linux_link_speed():
    # Try iwconfig
    out = run_cmd('iwconfig 2>/dev/null')
    speed = parse_linux_iwconfig(out)
    if speed:
        return speed
    # Try iw dev wlan0 link
    out2 = run_cmd('iw dev wlan0 link 2>/dev/null')
    speed = parse_linux_iwconfig(out2)
    if speed:
        return speed
    # Try nmcli (NetworkManager)
    out3 = run_cmd("nmcli -t -f ACTIVE,SSID,BITRATE dev wifi | grep '^yes' 2>/dev/null")
    m = re.search(r'([\\d\\.]+)M', out3)
    if m:
        return float(m.group(1))
    return None

def parse_macos_airport(output):
    # airport -I output contains "lastTxRate: 866" or "agrCtlRSSI"
    m = re.search(r'lastTxRate:\\s*([\\d\\.]+)', output)
    if m:
        return float(m.group(1))
    m2 = re.search(r'([\\d\\.]+)\\s*Mb/s', output)
    if m2:
        return float(m2.group(1))
    return None

def get_macos_link_speed():
    # airport utility path
    airport_path = '/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport'
    out = run_cmd(f"{airport_path} -I 2>/dev/null")
    speed = parse_macos_airport(out)
    return speed

def get_link_speed():
    p = sys.platform
    try:
        if p.startswith('win'):
            return get_windows_link_speed()
        elif p.startswith('linux'):
            return get_linux_link_speed()
        elif p.startswith('darwin'):
            return get_macos_link_speed()
    except Exception:
        return None
    return None

# ----------------------------- Speedtest helpers -----------------------------
def run_speedtest(progress_callback=None):
    # Try python module first
    try:
        from speedtest import Speedtest
        s = Speedtest()
        s.get_best_server()
        if progress_callback: progress_callback('Running download test...')
        dl = s.download()
        if progress_callback: progress_callback('Running upload test...')
        ul = s.upload()
        ping = s.results.ping
        return {'download_bps': dl, 'upload_bps': ul, 'ping_ms': ping, 'timestamp': datetime.now()}
    except Exception:
        # Fallback: try CLI `speedtest-cli --json`
        prog = shutil.which('speedtest-cli') or shutil.which('speedtest')
        if not prog:
            raise RuntimeError('speedtest module/CLI not found. Install with: pip install speedtest-cli or install Ookla Speedtest CLI.')
        # Try common json flags
        for args in ([prog, '--json'], [prog, '--format=json'], [prog, '--json']):
            try:
                proc = subprocess.run(args, capture_output=True, text=True, timeout=300)
                out = proc.stdout.strip()
                if not out:
                    out = proc.stderr.strip()
                data = json.loads(out)
                # different CLI produce different fields; try to parse robustly
                ping = data.get('ping') or data.get('server', {}).get('ping', None) or float(data.get('latency', 0))
                dl = data.get('download') or data.get('bytes_sent', None) or data.get('downloadBytes', None)
                ul = data.get('upload') or data.get('bytes_received', None) or data.get('uploadBytes', None)
                # if values in bits vs bytes, many CLIs already return bps for download/upload
                if dl is None or ul is None:
                    # try nested structure
                    try:
                        dl = float(data['download']['bandwidth']) * 8
                        ul = float(data['upload']['bandwidth']) * 8
                    except Exception:
                        pass
                return {'download_bps': float(dl), 'upload_bps': float(ul), 'ping_ms': float(ping), 'timestamp': datetime.now()}
            except Exception:
                continue
        raise RuntimeError('Unable to run speedtest via module or CLI.')

# ----------------------------- UI -----------------------------
def human_bps(bps):
    # human-friendly representation
    if bps is None:
        return 'N/A'
    units = ['bps','Kbps','Mbps','Gbps']
    val = float(bps)
    i = 0
    while val >= 1000 and i < len(units)-1:
        val /= 1000.0
        i += 1
    return f'{val:.2f} {units[i]}'

class WifiSpeedApp:
    def __init__(self, root):
        self.root = root
        root.title(APP_TITLE)
        root.geometry('520x380')
        root.resizable(False, False)

        frm = ttk.Frame(root, padding=12)
        frm.pack(fill='both', expand=True)

        # Link speed frame
        link_lab = ttk.Label(frm, text='Wi‑Fi Link Speed (adapter):', font=('Segoe UI', 10, 'bold'))
        link_lab.grid(row=0, column=0, sticky='w')

        self.link_var = tk.StringVar(value='--')
        ttk.Label(frm, textvariable=self.link_var, font=('Segoe UI', 12)).grid(row=1, column=0, sticky='w')

        self.refresh_btn = ttk.Button(frm, text='Refresh Link Speed', command=self.refresh_link_speed)
        self.refresh_btn.grid(row=1, column=1, padx=8)

        # Speedtest frame
        st_lab = ttk.Label(frm, text='Internet Speed Test (speedtest.net):', font=('Segoe UI', 10, 'bold'))
        st_lab.grid(row=2, column=0, pady=(16, 0), sticky='w')

        self.ping_var = tk.StringVar(value='Ping: --')
        self.dl_var = tk.StringVar(value='Download: --')
        self.ul_var = tk.StringVar(value='Upload: --')
        self.status_var = tk.StringVar(value='Ready')

        ttk.Label(frm, textvariable=self.ping_var).grid(row=3, column=0, sticky='w')
        ttk.Label(frm, textvariable=self.dl_var).grid(row=4, column=0, sticky='w')
        ttk.Label(frm, textvariable=self.ul_var).grid(row=5, column=0, sticky='w')

        self.test_btn = ttk.Button(frm, text='Run Speedtest', command=self.start_speedtest_thread)
        self.test_btn.grid(row=3, column=1, rowspan=2, padx=8)

        ttk.Label(frm, textvariable=self.status_var).grid(row=6, column=0, columnspan=2, pady=(12, 0), sticky='w')

        # Log area
        ttk.Label(frm, text='Log:', font=('Segoe UI', 10, 'bold')).grid(row=7, column=0, pady=(12, 0), sticky='w')
        self.log_text = tk.Text(frm, height=8, width=62, state='disabled')
        self.log_text.grid(row=8, column=0, columnspan=2, pady=(4,0))

        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=9, column=0, columnspan=2, pady=8, sticky='e')
        ttk.Button(btn_frame, text='Save Log...', command=self.save_log).pack(side='right')
        ttk.Button(btn_frame, text='Clear Log', command=self.clear_log).pack(side='right', padx=6)

        # initial read
        self.log(f'App started on {platform.system()} ({platform.platform()})')
        self.refresh_link_speed()

    # -------------------- UI helpers --------------------
    def log(self, text):
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        full = f'[{ts}] {text}\\n'
        self.log_text.configure(state='normal')
        self.log_text.insert('end', full)
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def clear_log(self):
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.configure(state='disabled')

    def save_log(self):
        file = filedialog.asksaveasfilename(defaultextension='.txt', initialfile=LOG_FILE_DEFAULT,
                                            filetypes=[('Text files','*.txt'),('All files','*.*')])
        if not file:
            return
        with open(file, 'w', encoding='utf-8') as f:
            f.write(self.log_text.get('1.0', 'end'))
        messagebox.showinfo('Saved', f'Log saved to: {file}')

    # -------------------- Link speed --------------------
    def refresh_link_speed(self):
        self.refresh_btn.config(state='disabled')
        self.status_var.set('Refreshing link speed...')
        def job():
            try:
                speed = get_link_speed()
                if speed is None:
                    self.link_var.set('Unknown or not connected')
                    self.log('Link speed: unknown')
                else:
                    self.link_var.set(f'{speed:.1f} Mbps')
                    self.log(f'Link speed: {speed:.1f} Mbps')
            except Exception as e:
                self.link_var.set('Error')
                self.log(f'Error reading link speed: {e}')
            finally:
                self.status_var.set('Ready')
                self.refresh_btn.config(state='normal')
        threading.Thread(target=job, daemon=True).start()

    # -------------------- Speedtest --------------------
    def start_speedtest_thread(self):
        self.test_btn.config(state='disabled')
        self.refresh_btn.config(state='disabled')
        self.status_var.set('Starting speedtest...')
        threading.Thread(target=self._run_speedtest, daemon=True).start()

    def _run_speedtest(self):
        try:
            if Speedtest is None:
                raise RuntimeError('speedtest module not installed. Run: pip install speedtest-cli')
            self.log('Speedtest: selecting best server...')
            def progress(msg):
                self.status_var.set(msg)
            res = run_speedtest(progress_callback=progress)
            dl = res['download_bps']
            ul = res['upload_bps']
            ping = res['ping_ms']
            self.ping_var.set(f'Ping: {ping:.1f} ms')
            self.dl_var.set(f'Download: {human_bps(dl)}')
            self.ul_var.set(f'Upload: {human_bps(ul)}')
            self.log(f"Speedtest result - Ping: {ping:.1f} ms, Download: {human_bps(dl)}, Upload: {human_bps(ul)}")
            self.status_var.set('Speedtest completed')
        except Exception as e:
            self.status_var.set('Error during speedtest')
            self.log(f'Speedtest error: {e}')
            messagebox.showerror('Speedtest error', str(e))
        finally:
            self.test_btn.config(state='normal')
            self.refresh_btn.config(state='normal')

# ----------------------------- Entry point -----------------------------
def main():
    root = tk.Tk()
    app = WifiSpeedApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()
