#!/usr/bin/env python

# Sonic FreeBee DAC
# licensed under Apache License 2.0
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# (c) Sonic Designs Ltd., 2017
#
# Dependencies: python-gobject python-gst0.10 gstreamer0.10-plugins-good

import signal
import sys
import gobject
gobject.threads_init()
import pygst
pygst.require('0.10')
import gst
import socket

BANDS = 16
INTERVAL = 100
MPD_FIFO = '/run/mpd/mpd.fifo'
THRESHOLD = -100
MCAST_GRP = '224.1.1.1'
MCAST_PORT = 5007

class SigtermException(Exception):
    pass

def sigterm_handler(signum, frame):
    raise SigtermException()

def log_error(msg):
    sys.stderr.write("{0}\n".format(msg))
    sys.stderr.flush()

class AudioDataMulticaster(object):
    def __init__(self, mpd_fifo, interval, bands, threshold, mcast_grp, mcast_port):
        self.init_pipeline(mpd_fifo, interval, bands, threshold)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        self.mcast_addr = (MCAST_GRP, MCAST_PORT)

    def init_pipeline(self, mpd_fifo, interval, bands, threshold):
        pipeline = ['filesrc location={} ! audio/x-raw-int, ' \
                    'rate=44100, channels=2, endianness=1234, width=16, depth=16, ' \
                    'signed=true ! audioconvert'.format(mpd_fifo)]
        ival = 'interval={}'.format(1000000 * interval)
        pipeline.append('level message=true {}'.format(ival))
        pipeline.append('spectrum message=true {} bands={} threshold={} multi-channel=true'.format(ival, bands, threshold))
        pipeline.append('fakesink')
        self.pipeline = gst.parse_launch(' ! '.join(pipeline))

    def sock_send(self, msg):
        self.sock.sendto(msg, self.mcast_addr)

    def on_audio_data(self, bus, data):
        try:
            struct = data.structure
            name = struct.get_name()
            msg = '{'
            if name == 'spectrum':
                msg = msg + '"spectrum":{"magnitude":['
                mags = struct['magnitude']
                l = len(mags)
                for ch in range(l):
                    ch_mags = ','.join(str(int(round(d))) for d in mags[ch])
                    msg = msg + '[{}]'.format(ch_mags)
                    if ch < l - 1:
                        msg = msg + ','
                msg = msg + ']}}'
            elif name == 'level':
                msg = msg + '"level":{"peak":['
                peaks = struct['peak']
                decays = struct['decay']
                decay = '],"decay":['
                l = len(peaks)
                for ch in range(l):
                    msg = msg + str(int(round(peaks[ch])))
                    decay = decay + str(int(round(decays[ch])))
                    if ch < l - 1:
                        msg = msg + ','
                        decay = decay + ','
                msg = msg + decay + "]}}"
            else:
                return True
            try:
                #print(msg)
                self.sock_send(msg)
            except socket.error as err:
                log_error(err)
        except SigtermException:
            self.loop.quit()
        return True

    def start(self):
        self.bus = self.pipeline.get_bus()
        self.bus.enable_sync_message_emission()
        self.bus.add_signal_watch()
        self.conn_handler = self.bus.connect("message::element", self.on_audio_data)
        self.pipeline.set_state(gst.STATE_PLAYING)

    def stop(self):
        if self.pipeline:
            self.bus.disconnect(self.conn_handler)
            self.bus.remove_signal_watch()
            self.pipeline.set_state(gst.STATE_NULL)

    def run(self):
        try:
            self.start()
            self.loop = gobject.MainLoop()
            try:
                self.loop.run()
            except SigtermException:
                pass
            self.stop()
            exit(0)
        except gobject.GError as err:
            log_error(err)
            exit(1)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, sigterm_handler)
    adm = AudioDataMulticaster(MPD_FIFO, INTERVAL, BANDS, THRESHOLD, MCAST_GRP, MCAST_PORT)
    adm.run()
