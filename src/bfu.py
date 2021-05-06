#!/usr/bin/env python3
# Bluetooth Firmware Update
# Author: Alexander "goodmice" Sirotkin
# Created Date: 2021-04-29
# Updated Date: 2021-05-06

import sys
import time
import os.path
import argparse
import mimetypes
from warnings import warn
from bluetooth import *
from zlib import crc32
from struct import pack_into

from typing import Union, Callable, List, Optional

class Context:
    def __init__(self, msg: str = None, **kwargs):
        self.glob: bool = True
        self.msg: str = msg
        self.ok_msg: str = kwargs.pop('ok', 'OK')
        self.info_msg: str = kwargs.pop('info', 'INFO')
        self.err_msg: str = kwargs.pop('err', 'ERR ')
        self.warn_msg: str = kwargs.pop('warn', 'WARN')
        self.required: bool = kwargs.pop('required', True)
        self.proc = False

    def pos(self, proc: bool = True) -> None:
        if self.inline:
            print()
            self.inline = False
        if proc and self.proc:
            sys.stdout.write(' '*(os.get_terminal_size().columns)+'\r')
            sys.stdout.flush()
        if not self.glob:
            print('\t', end='', flush=True)

    def progress(self, cur_v: int, max_v: int, start_time: Optional[float] = None):
        self.pos(False)
        size: int = os.get_terminal_size().columns

        template: str = '[INFO] Progress: [{0:%d}] {1:3}%%'
        if start_time is not None:
            template += ' %3d s' % (time.time() - start_time)
        
        max_c: int = max(size - len(template), 0)
        sys.stdout.write((template % max_c).format('*'*int(cur_v/max_v*max_c), cur_v*100//max_v))
        if cur_v < max_v:
            sys.stdout.write('\r')
            sys.stdout.flush()
        else:
            print()
        self.proc = cur_v < max_v

    def info(self, msg) -> None:
        self.pos()
        print('[%-4s]' % self.info_msg, msg)

    def warn(self, msg) -> None:
        self.pos()
        print('[%-4s]' % self.warn_msg, msg)

    def err(self, msg) -> None:
        self.pos()
        print('[%-4s]' % self.err_msg, msg)

    def __enter__(self):
        print('[INFO]', self.msg + '...', end='', flush=True)
        self.inline: bool = True
        self.glob = False
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is None:
            if self.inline:
                print(self.ok_msg)
            return
        if not exc_val or len(str(exc_val)) == 0:
            exc_val = 'Unknown'
        exc_val = str(exc_val)
        if not self.required:
            if self.inline:
                print(self.warn_msg)
            self.warn(exc_val + '!')
        else:
            if self.inline:
                print(self.err_msg)
                self.inline = False
            self.err(exc_val + '! Exiting...')
            exit(1)

class FirmwareUpdater:
    UPD_BEG = b'\xAA'
    UPD_ERR = b'\xEE'
    UPD_END = b'\xFF'

    PKG_ACK = b'\xFF'
    PKG_ERR = b'\xEE'
    PKG_PAN = b'\xAA'

    PKG_SIZE = 2
    CRC_SIZE = 4

    def __init__(self, addr: str, path: str, **kwargs):
        self.addr: str = addr
        self.path: str = path
        self.timeout: int = kwargs.pop('timeout', 1)
        self.packsize: int = kwargs.pop('packsize', 512) - FirmwareUpdater.CRC_SIZE - FirmwareUpdater.PKG_SIZE
        self.attempts: int = kwargs.pop('attempts', 3)
        self.verbose: int = kwargs.pop('verbose', 0)

        with Context('Trying connect to target device'):
            service_matches = find_service(address=addr)
            if len(service_matches) == 0:
                raise Exception('Device not found')
            first_match = service_matches[0]
            self.sock: BluetoothSocket = BluetoothSocket(RFCOMM)
            self.sock.connect((first_match["host"], first_match["port"]))
            self.sock.settimeout(self.timeout)

    def prepare_packets(self) -> List[bytes]:
        result: List[bytes] = []
        with open(self.path, 'rb') as f:
            self.full_size = 0
            size: int = os.path.getsize(self.path)
            while size > 0:
                dat_size: int = min(self.packsize, size)
                dat: bytes = f.read(dat_size)
                crc: bytes = crc32(dat).to_bytes(4, byteorder='little', signed=False)
                ds_byte: bytes = dat_size.to_bytes(2, byteorder='little', signed=False)

                result.append(bytes(b''.join([ds_byte, crc, dat])))
                self.full_size += len(result[-1])
                size -= dat_size
        return result

    @staticmethod
    def list_devices() -> None:
        with Context('Script is looking for devices'):
            nearby_devices: list = discover_devices(lookup_names = True)
        with Context('Found %d devices' % len(nearby_devices)) as c:
            for i, (addr, name) in enumerate(nearby_devices):
                c.info('Device %d => %s \t %s' % (i, addr, name))

    def send_packet(self, packet: bytes) -> bool:
        for i in range(self.attempts):
            self.sock.send(packet)
            ret = self.sock.recv(1)
            if ret == FirmwareUpdater.PKG_ACK:
                return True
            elif ret == FirmwareUpdater.PKG_PAN:
                return False
        self.sock.send(FirmwareUpdater.UPD_ERR)
        return False

    def upload_firmware(self) -> None:
        with Context('Prepairing packets') as c:
            self.packets = self.prepare_packets()
        with Context('Starting transaction') as c:
            self.sock.send(b'firmware_update')
            self.sock.recv(1)
            self.sock.send(FirmwareUpdater.UPD_BEG)
            if self.sock.recv(1) != FirmwareUpdater.PKG_ACK:
                raise Exception('Transfer did not begin')
        with Context('Sending packets') as c:
            start_time = time.time()
            for i, p in enumerate(self.packets):
                c.progress(i + 1, len(self.packets), start_time)
                if not self.send_packet(p):
                    raise Exception('packet %d/%d send error' % (i + 1, len(self.packets)))
            self.full_time = time.time() - start_time
            c.info('Full size: %d bytes' % self.full_size)
            c.info('Loading time: %5.2f s' % self.full_time)
            c.info('Average speed: %5.2f KB/s' % (self.full_size / self.full_time / 1024))
        with Context('Ending transaction') as c:
            self.sock.send(FirmwareUpdater.UPD_END)
            if self.sock.recv(1) != FirmwareUpdater.PKG_ACK:
                raise Exception()

def check_size(parser: argparse.ArgumentParser, size: int) -> bool:
    if size <= 0:
        parser.error('Size must be positive!')
    if size > 512:
        parser.error('Size must be no more than 512!')
    return size

def check_file(parser: argparse.ArgumentParser, path: str) -> str:
    if not os.path.exists(path):
        parser.error('The file %s does not exist!' % path)
    if not os.path.isfile(path):
        parser.error('%s is not file!' % path)
    if mimetypes.guess_type(path)[0] != 'application/octet-stream':
        parser.error('The file %s of the wrong type!' % path)
    return path

def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(prog='bfu', description='Uploads Firmware to ESP32 on Bluetooth.')
    parser.add_argument('--version', action='version', version='%(prog)s 0.1')
    parser.add_argument('-a', '--attemtps', type=int, default=3, help='number of attempts to resend packet')
    parser.add_argument('-p', '--packsize', type=lambda x: check_size(parser, int(x)), default=512, help='packsize in bytes')
    parser.add_argument('-v', '--verbose', action='count', default=0, help='verbose output level')
    parser.add_argument('-l', '--list', action='store_true', help='print list of available devices')
    parser.add_argument('-t', '--target', metavar='TARGET', type=str, help='target device UUID')
    parser.add_argument('-n', '--name', metavar='TARGET', type=str, help='target device name')
    parser.add_argument('path', metavar='PATH', type=lambda x: check_file(parser, x), help='path to firmware binary file', nargs='?')
    args: object = parser.parse_args()

    if args.list:
        FirmwareUpdater.list_devices()
        exit(0)

    if args.target:
        target = args.target
    elif args.name:
        with Context('Finding device with name') as c:
            nearby_devices: list = discover_devices(lookup_names = True)
            for addr, name in nearby_devices:
                if args.name in name:
                    target = addr
                    break
            else:
                raise Exception('Device not found')
        c.info('Device UUID: %s' % target)
    else:
        parser.error('Target UUID or name must be specified!')
        parser.exit(1)

    fu = FirmwareUpdater(target, args.path, verbose=args.verbose, packsize=args.packsize)
    fu.upload_firmware()

if __name__ == '__main__':
    main()
