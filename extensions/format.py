import struct

class pack:
    @staticmethod
    def int16l(val):
        return struct.pack("<h", val)

    @staticmethod
    def int32l(val):
        return struct.pack("<i", val)

    @staticmethod
    def float32l(val):
        return struct.pack("<f", val)
    
    @staticmethod
    def float16l(val):
        return struct.pack("<e", val)

    @staticmethod
    def byte(val):
        val=min(255,max(0,int(val)))
        return bytes(val)

class unpack:
    @staticmethod
    def int16l(data):
        return struct.unpack("<h", data)[0]

    @staticmethod
    def int32l(data):
        return struct.unpack("<i", data)[0]

    @staticmethod
    def float32l(data):
        return struct.unpack("<f", data)[0]

    @staticmethod
    def float16l(data):
        return struct.unpack("<e", data)[0]

    @staticmethod
    def byte(data):
        return data[0]