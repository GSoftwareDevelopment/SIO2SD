# Device server for Altirra custom devices (V2 / Altirra 4.0 protocol)
# Copyright (C) 2020 Avery Lee, All rights reserved.
#
# This software is provided 'as-is', without any express or implied
# warranty.  In no event will the authors be held liable for any
# damages arising from the use of this software.
# 
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely, subject to the following restrictions:
# 
# 1. The origin of this software must not be misrepresented; you must
#    not claim that you wrote the original software. If you use this
#    software in a product, an acknowledgment in the product
#    documentation would be appreciated but is not required.
# 2. Altered source versions must be plainly marked as such, and must
#    not be misrepresented as being the original software.
# 3. This notice may not be removed or altered from any source
#    distribution.
#
# Wersja zmieniona: skrocono czesc docstringow. Oryginal znajduje sie
# w dystrybucji Altirry oraz w repozytorium fujinet-emulator-bridge.


import socketserver
import struct
import signal
import sys
import argparse

class DeviceSegment:
    """
    Proxy for Segment variables in the device script.
    """

    __slots__ = ['handler', 'segment_index']

    def __init__(self, handler, segment_index):
        self.handler = handler
        self.segment_index = segment_index

    def read(self, offset: int, len: int):
        """
        Read data from [offset:offset+len] in the segment.
        """
        return self.handler.req_read_seg_mem(self.segment_index, offset, len)

    def write(self, offset: int, data:bytes):
        """
        Write data to [offset:offset+len] in the segment.
        """
        return self.handler.req_write_seg_mem(self.segment_index, offset, data)

    def fill(self, offset: int, val: int, len: int):
        """
        Fill [offset:offset+len] with byte val.
        """

        return self.handler.req_fill_seg_mem(self.segment_index, offset, val, len)

    def copy(self, dst_offset: int, src_segment: 'DeviceSegment', src_offset: int, len: int):
        """
        Copy src_segment[src_offset:src_offset+len] to dst_offset[dst_offset:dst_offset+len].
        """

        return self.handler.req_copy_seg_mem(self.segment_index, dst_offset, src_segment.segment_index, src_offset, len)

class DeviceMemoryLayer:
    """
    Proxy for MemoryLayer variables in the device script.
    """

    __slots__ = ['handler', 'layer_index']

    def __init__(self, handler, layer_index):
        self.handler = handler
        self.layer_index = layer_index

    def enable(self, read: bool, write: bool):
        """
        Enable or disable the memory layer for read and write memory accesses.
        """

        self.handler.req_enable_layer(self.layer_index, read, write)

    def set_offset(self, offset: int):
        """
        Set the starting byte offset of a direct mapped layer within the mapped segment.
        """

        self.handler.req_set_layer_offset(self.layer_index, offset)

    def set_segment_and_offset(self, segment: DeviceSegment, segment_offset: int):
        """
        Set the mapped segment and starting byte offset for a direct mapped layer.
        """

        self.handler.req_set_layer_segment_and_offset(self.layer_index, segment.segment_index, segment_offset)

    def set_readonly(self, ro: bool):
        """
        Set the read-only status of a layer, controlling whether writes to the layer
        change the data in the mapped segment.
        """

        self.handler.req_set_layer_readonly(self.layer_index, ro)

class DeviceTCPHandler(socketserver.BaseRequestHandler):
    """
    Base socketserver handler for implementing the custom device server
    protocol. You should subclass this type in your own code and implement
    handle_*() methods. Use req_*() methods or the methods on the reflected
    device objects to call back into the emulator.

    For convenience, memory layers and segment variables are reflected from the
    device script back into this handler to allow them to be referred to by name,
    isolating the server from some changes in the device script. A segment variable
    'foo' becomes self.seg_foo, and a memory layer 'bar' becomes self.layer_bar.
    """

    def __init__(self, *args, **kwargs):
        self.verbose = False
        self.handlers = {};

        self.handlers[0] = ("None", self.handle_none)
        self.handlers[1] = ("Debug read byte", self.wrap_debugreadbyte)
        self.handlers[2] = ("Read byte", self.wrap_readbyte)
        self.handlers[3] = ("Write byte", self.wrap_writebyte)
        self.handlers[4] = ("Cold reset", self.wrap_coldreset)
        self.handlers[5] = ("Warm reset", self.wrap_warmreset)
        self.handlers[6] = ("Error", self.handle_error)
        self.handlers[7] = ("Script event", self.wrap_script_event)
        self.handlers[8] = ("Script post", self.handle_script_post)

        self.counter = 0

        super().__init__(*args, **kwargs)

    def handle(self):
        """
        Main protocol service loop.
        """

        self.verbose = self.server.cmdline_args.verbose

        self.log("Connection received from emulator")

        while True:
            command_packet = bytearray()

            while len(command_packet) < 17:
                command_subpacket = self.request.recv(17 - len(command_packet))
                if len(command_subpacket) == 0:
                    self.log("Connection closed")
                    return

                command_packet.extend(command_subpacket)

            command_id, param1, param2, timestamp = struct.unpack('<BIiQ', command_packet)
            self.verbose = self.server.cmdline_args.verbose

            try:
                command_name, handler = self.handlers[command_id]
            except KeyError:
                self.log("Unhandled command {:02X} - closing connection.".format(command_id))
                return

            if self.verbose:
                self.log("{1:016X} {0}({2:08X}, {3:08X})".format(command_name, timestamp, param1, param2))

            handler(param1, param2, timestamp)

    def log(self, msg):
        cb = getattr(self.server, 'event_log', None)
        if cb:
            cb(str(msg))
        else:
            print(msg)

    #----------------------------------------------------------------------------------
    # Raw extension points
    #
    def wrap_debugreadbyte(self, address, param2, timestamp) -> int:
        rvalue = self.handle_debugreadbyte(address, timestamp)

        self.request.sendall(struct.pack('<Bi', 1, rvalue))

    def wrap_readbyte(self, address, param2, timestamp) -> int:
        rvalue = self.handle_readbyte(address, timestamp)

        self.request.sendall(struct.pack('<Bi', 1, rvalue))

    def wrap_writebyte(self, param1, param2, timestamp) -> int:
        self.handle_writebyte(param1, param2, timestamp)
        self.request.sendall(b'\x01\0\0\0\0')

    def wrap_coldreset(self, param1, param2, timestamp) -> int:
        # The V1 protocol unfortunately lacks an extension point and rejects unknown
        # calls, so the host abuses the cold reset command with different parameters as
        # the init command to detect downlevel hosts. We do not support V1 hosts here
        # but must still play along.
        if param2 >= 0x7F000001 and param2 <= 0x7FFFFFFF:
            # tell host that we support V2 protocol
            self.request.sendall(b'\x0C\x02')
            self.wrap_init()

        self.handle_coldreset(timestamp)
        self.request.sendall(b'\x01\0\0\0\0')

    def wrap_warmreset(self, param1, param2, timestamp) -> int:
        self.handle_warmreset(timestamp)
        self.request.sendall(b'\x01\0\0\0\0')

    def wrap_script_event(self, param1, param2, timestamp) -> int:
        self.request.sendall(struct.pack('<Bi', 1, self.handle_script_event(param1, param2, timestamp)))

    def wrap_init(self):
        self.reflect_vars()

    #----------------------------------------------------------------------------------
    # Extension points
    #

    def handle_none(self, param1, param2, timestamp) -> int:
        pass

    def handle_debugreadbyte(self, address, timestamp) -> int:
        return self.counter

    def handle_readbyte(self, address, timestamp) -> int:
        v = self.counter
        self.counter = (self.counter + 1) & 0xFF
        return v

    def handle_writebyte(self, address, value, timestamp) -> None:
        self.counter = value

    def handle_init(self) -> None:
        pass

    def handle_coldreset(self, timestamp) -> None:
        pass

    def handle_warmreset(self, timestamp) -> None:
        pass

    def handle_error(self, param1, param2, timestamp) -> int:
        msg = self._readall(param2).decode('utf-8')
        self.log("Error from emulator: " + msg)
        return 0

    def handle_script_event(self, param1, param2, timestamp) -> int:
        return 0

    def handle_script_post(self, param1, param2, timestamp) -> None:
        pass

    #----------------------------------------------------------------------------------
    # Request functions
    #

    def req_enable_layer(self, layer_index: int, read: bool, write: bool):
        self.request.sendall(struct.pack('<BBB', 2, layer_index, (2 if read else 0) + (1 if write else 0)))

    def req_set_layer_offset(self, layer_index: int, offset: int):
        if offset < 0 or offset & 255:
            raise ValueError('Invalid segment offset')

        self.request.sendall(struct.pack('<BBI', 3, layer_index, offset))

    def req_set_layer_segment_and_offset(self, layer_index: int, segment_index: int, segment_offset: int):
        if segment_offset < 0 or segment_offset & 255:
            raise ValueError('Invalid segment offset')

        self.request.sendall(struct.pack('<BBBI', 4, layer_index, segment_index, segment_offset))

    def req_set_layer_readonly(self, layer_index: int, ro: bool):
        self.request.sendall(struct.pack('<BBB', 5, layer_index, 1 if ro else 0))

    def req_read_seg_mem(self, segment_index: int, offset: int, len: int):
        if offset < 0:
            raise ValueError('Invalid segment offset')

        if len <= 0:
            if len == 0:
                return bytes()

            raise ValueError('Invalid length')


        self.request.sendall(struct.pack('<BBII', 6, segment_index, offset, len))
        return self._readall(len)

    def req_write_seg_mem(self, segment_index: int, offset: int, data:bytes):
        if offset < 0:
            raise ValueError('Invalid segment offset')

        if len(data) == 0:
            return

        self.request.sendall(struct.pack('<BBII', 7, segment_index, offset, len(data)))
        self.request.sendall(data)

    def req_fill_seg_mem(self, segment_index: int, offset: int, val: int, len: int):
        if offset < 0:
            raise ValueError('Invalid segment offset')

        if len <= 0:
            if len == 0:
                return

            raise ValueError('Invalid fill length')

        self.request.sendall(struct.pack('<BBIBI', 13, segment_index, offset, val, len))

    def req_copy_seg_mem(self, dst_segment_index: int, dst_offset: int, src_segment_index: int, src_offset: int, len: int):
        if dst_offset < 0:
            raise ValueError('Invalid destination segment offset')

        if src_offset < 0:
            raise ValueError('Invalid source segment offset')

        if len < 0:
            raise ValueError('Invalid copy length')

        if len > 0:
            self.request.sendall(struct.pack('<BBIBII', 8, dst_segment_index, dst_offset, src_segment_index, src_offset, len))

    def req_interrupt(self, aux1: int, aux2: int):
        self.request.sendall(struct.pack('<BII', 9, aux1, aux2))

    def req_get_segment_names(self):
        self.request.sendall(b'\x0A')
        return self._read_names()

    def req_get_layer_names(self):
        self.request.sendall(b'\x0B')
        return self._read_names()

    def reflect_vars(self):
        for segment_index, segment_name in enumerate(self.req_get_segment_names(), start=0):
            setattr(self, "seg_" + segment_name, DeviceSegment(self, segment_index))

        for layer_index, layer_name in enumerate(self.req_get_layer_names(), start=0):
            setattr(self, "layer_" + layer_name, DeviceMemoryLayer(self, layer_index))

    def _read_names(self):
        num_names = struct.unpack('<I', self._readall(4))[0]
        names = []

        for i in range(0, num_names):
            name_len = struct.unpack('<I', self._readall(4))[0]
            names.append(self._readall(name_len).decode('utf-8'))

        return names

    def _readall(self, readlen):
        seg_data = bytearray()
        while len(seg_data) < readlen:
            seg_subdata = self.request.recv(readlen - len(seg_data))
            if len(seg_subdata) == 0:
                raise ConnectionError

            seg_data.extend(seg_subdata)

        return seg_data

def print_banner():
    print("Altirra Custom Device Server v0.8")
    print()

def run_deviceserver(
    handler: type,
    port: int = 6502,
    arg_parser = argparse.ArgumentParser(description = "Starts a localhost TCP server to handle emulator requests for a custom device."),
    run_handler = None,
    post_argparse_handler = None
):
    """
    Bootstrap the device server.
    """

    print_banner()

    arg_parser.add_argument('--port', type=int, default=port, help='Change TCP port (default: {})'.format(port))
    arg_parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', help='Log emulation device commands')

    args = arg_parser.parse_args()

    if post_argparse_handler is not None:
        post_argparse_handler(args)

    with socketserver.TCPServer(("localhost", args.port), handler) as server:
        server.cmdline_args = args

        print("Waiting for localhost connection from emulator on port {} -- Ctrl+Break to stop".format(args.port))

        if run_handler is not None:
            run_handler(server)
        else:
            server.serve_forever()

if __name__ == '__main__':
    print_banner()
    print("""deviceserver.py is not meant to be run directly. It is a framework for
building your own device server to be used with a custom device specified in an
.atdevice file.""")
