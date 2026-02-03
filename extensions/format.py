import struct


def int16l(val):
    return struct.pack("<h", val)

def float16l(val):
    return struct.pack("<e", val)

def byte(val):
    val=min(255,max(0,int(val)))
    return bytes(val)