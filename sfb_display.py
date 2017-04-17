#!/usr/bin/env python3

# Sonic FreeBee Display
# licensed under Apache License 2.0
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# (c) Sonic Designs Ltd., 2017
#
# Prerequisite: curl -sS get.pimoroni.com/displayotron | bash

import signal
import sys
import socket
import struct
import json
import dothat.backlight as backlight
import dothat.lcd as lcd

MCAST_GRP = '224.1.1.1'
MCAST_PORT = 5007

COLOUR_RED = [255, 0, 0]
COLOUR_YELLOW = [255, 255, 0]
COLOUR_GREEN = [0, 255, 0]
COLOUR_CYAN = [0, 255, 255]
COLOUR_BLUE = [0, 0, 255]
COLOUR_MAGENTA = [255, 0, 255]

SPECTRUM_CHARS = [
    [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF],
    [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF],
    [0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF],
    [0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF],
    [0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF],
    [0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF],
    [0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF],
    [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
]
SPECTRUM_CHARS_FLIP = [
    [0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    [0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    [0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00],
    [0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00],
    [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00],
    [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00],
    [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00],
    [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
]

flipped = False

def init_display():
    backlight.graph_set_led_duty(0, 1)
    if flipped:
       for i in range(len(SPECTRUM_CHARS_FLIP)):
           lcd.create_char(i, SPECTRUM_CHARS_FLIP[i])
    else:
       for i in range(len(SPECTRUM_CHARS)):
           lcd.create_char(i, SPECTRUM_CHARS[i])

class SigtermException(Exception):
    pass

def sigterm_handler(signum, frame):
    raise SigtermException()

def log_error(msg):
    sys.stderr.write("{0}\n".format(msg))
    sys.stderr.flush()

class AudioDataPresenter(object):
    def __init__(self, mcast_grp, mcast_port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((mcast_grp, mcast_port))
        mreq = struct.pack("4sl", socket.inet_aton(mcast_grp), socket.INADDR_ANY)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    def lcd_magnitudes(self, magnitudes):
        magn_int = [round(m * 24.0) for m in magnitudes]
        for i in range(len(magn_int)):
            m = magn_int[i]
            full_chars = m // 8
            for j in range(full_chars):
                lcd.set_cursor_position(i, 2 - j)
                lcd.write(chr(7))
            fract_char = m % 8
            if fract_char > 0:
                lcd.set_cursor_position(i, 2 - full_chars)
                lcd.write(chr(fract_char - 1))
            elif full_chars < 3:
                lcd.set_cursor_position(i, 2 - full_chars)
                lcd.write(' ')
            for j in range(full_chars + 1, 3):
                lcd.set_cursor_position(i, 2 - j)
                lcd.write(' ')

    def backlight_magnitudes(self, magnitudes):
        brightness = sum(magnitudes[:3]) / 3.0
        colours = [round(c * brightness) for c in COLOUR_RED]
        backlight.single_rgb(0, colours[0], colours[1], colours[2])
        brightness = sum(magnitudes[3:5]) / 2.0
        colours = [round(c * brightness) for c in COLOUR_YELLOW]
        backlight.single_rgb(1, colours[0], colours[1], colours[2])
        brightness = sum(magnitudes[5:8]) / 3.0
        colours = [round(c * brightness) for c in COLOUR_GREEN]
        backlight.single_rgb(2, colours[0], colours[1], colours[2])
        brightness = sum(magnitudes[8:11]) / 3.0
        colours = [round(c * brightness) for c in COLOUR_CYAN]
        backlight.single_rgb(3, colours[0], colours[1], colours[2])
        brightness = sum(magnitudes[11:13]) / 2.0
        colours = [round(c * brightness) for c in COLOUR_BLUE]
        backlight.single_rgb(4, colours[0], colours[1], colours[2])
        brightness = sum(magnitudes[13:16]) / 3.0
        colours = [round(c * brightness) for c in COLOUR_MAGENTA]
        backlight.single_rgb(5, colours[0], colours[1], colours[2])

    def handle_spectrum(self, spectrum_data):
        magnitudes = []
        for m in zip(spectrum_data['magnitude'][0], spectrum_data['magnitude'][1]):
            magnitudes.append(sum(m) / len(m))
        m_min = min(magnitudes)
        m_range = max(magnitudes) - m_min
        if m_range == 0.0:
            magnitudes = [0.0] * 16
        else:
            magnitudes = [((m - m_min) / m_range) for m in magnitudes]
        self.lcd_magnitudes(magnitudes)
        self.backlight_magnitudes(magnitudes)

    def handle_level(self, level_data):
        peaks = level_data['peak']
        bar_height = round((sum(peaks) / len(peaks) + 100.0) / 100.0 * 6.0)
        for i in range(bar_height):
            backlight.graph_set_led_state(5 - i, 1)
        for i in range(bar_height, 6):
            backlight.graph_set_led_state(5 - i, 0)

    def run(self):
        try:
            while True:
                try:
                    msg_bytes = self.sock.recv(1024)
                    msg_str = str(msg_bytes, 'utf-8')
                    data = json.loads(msg_str)
                    if 'spectrum' in data:
                        self.handle_spectrum(data['spectrum'])
                    if 'level' in data:
                        self.handle_level(data['level'])
                except socket.error as err:
                    log_error(err)
        except SigtermException:
            pass

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, sigterm_handler)
    init_display()
    adp = AudioDataPresenter(MCAST_GRP, MCAST_PORT)
    adp.run()
