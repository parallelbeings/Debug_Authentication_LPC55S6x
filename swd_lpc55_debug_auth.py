import pyHydrabus
import hexdump as hexdump
import time
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.backends import default_backend

class Debugger():

    """Class debuuger methods were re-used from this blog
        https: // research.kudelskisecurity.com / 2019 / 07 / 31 / swd - part - 2 - the - mem - ap /
        Credits: research.kudelskisecurity.com ,  Nicolas Oberli.
    """

    def __init__(self, device):
        self.device = pyHydrabus.RawWire(device)
        self.device._config = 0xa  # Set GPIO open-drain / LSB first
        self.device._configure_port()

    def sync(self):
        self.device.write(b'\x00')

    def init(self):
        self.device.write(b'\xff\xff\xff\xff\xff\xff\xff\x7b\x9e\xff\xff\xff\xff\xff\xff\x0f')
        self.sync()

    def cal_parity_bit(self, value):
        tmp = value & 0b00011110
        if(bin(tmp).count('1')%2) == 1:
            value = value | 1<<5
        return value

    def read_dp(self, addr, ap=0):
        CMD = 0x85
        CMD = CMD | ap << 1
        CMD = CMD | (addr & 0b1100) << 1
        CMD = self.cal_parity_bit(CMD)

        self.device.write(CMD.to_bytes(1, byteorder="little"))

        status = 0
        for i in range(3):
            #ord() function returns the Unicode code from a given characteself.device.
            status += ord(self.device.read_bit()) << i
        if status == 1:
            retval = int.from_bytes(self.device.read(4), byteorder="little")
            self.sync()
            return retval
        else:
            self.sync()
            raise ValueError(f"Returned status is {hex(status) , bin(status)}")


    def write_dp(self, addr, value, ap=0):
        CMD = 0x81
        CMD = CMD | ap << 1
        CMD = CMD | (addr & 0b1100) << 1
        CMD = self.cal_parity_bit(CMD)

        self.device.write(CMD.to_bytes(1, byteorder="little"))

        status = 0
        for i in range(3):
            status += ord(self.device.read_bit()) << i
        self.device.clocks(2)
        if status != 1:
            self.sync()
            raise ValueError(f"Returned status is {hex(status), bin(status)}")
        self.device.write(value.to_bytes(4, byteorder="little"))

        if(bin(value).count('1')% 2) == 1:
            self.device.write(b'\x01')
        else:
            self.device.write(b'\x00')

    def read_ap(self, addr, bank):
        select_reg = 0
        select_reg = select_reg | addr << 24
        select_reg = select_reg | (bank & 0b11110000)

        self.write_dp(8, select_reg)
        self.read_dp((bank & 0b1100), ap=1)

        return self.read_dp(0xc)

    def write_ap(self, addr, bank,value):
        select_reg = 0
        select_reg = select_reg | addr << 24
        select_reg = select_reg | (bank & 0b11110000)

        self.write_dp(8, select_reg)
        self.write_dp((bank & 0b1100), value, ap=1)

    def halt_cpu(self):
        # Set MEM-AP TAR to 0xE000EDF0
        self.write_ap(0, 0x4, 0xE000EDF0)
        # Write to MEM-AP DRW, writing the DHCSR bits C_STOP and C_DEBUGEN
        self.write_ap(0, 0xc, 0xA05F0003)

    def run_cpu(self, ):
        self.write_ap(0, 0x4, 0xE000EDF0)
        self.write_ap(0, 0xc, 0xA05F0000)

class Misc():

    def __init__(self):
        self.name = None

    def int2bytes(self, i, enc):
        return i.to_bytes((i.bit_length() + 7) // 8, enc)

    def convert_hex(self, str, enc1, enc2):
        return self.int2bytes(int.from_bytes(bytes.fromhex(str), enc1), enc2).hex()

class Debug_Auth():

    """
    #Terminology
    #DAC - Debug Authentication Challenge
    #DAR - Debug Authentication Response
    """

    def __init__(self):
        self.name = None

    def request_DAC(self):
        print("-------------------------------------------------------------------------------")
        # Initialize DebugMailbox object - Write to CSW register by Set  the CHIP_RESET_REQ and the RESYNCH_REQ bit
        debugger.write_ap(2, 0x0, 0x00000021)
        time.sleep(2)
        # DebugAuthenticationStart DAC
        debugger.write_ap(2, 0x4, 0x00000010)
        val = debugger.read_ap(2, 0x8).to_bytes(4, byteorder="little")
        print("Request Debug Authentication Challenge from MCU: <--", bytearray(val).hex())
        print("-------------------------------------------------------------------------------")
        global buff
        buff = b''
        for i in range(26, 0, -1):
            ack = "0x0000a5a5"
            ack1 = format(i, '#06x')
            ack2 = ack[6:12]
            ack3 = (ack1 + ack2)[4:]
            ack4 = int(ack3, base=16)
            debugger.write_ap(2, 0x4, ack4)
            val = debugger.read_ap(2, 0x8).to_bytes(4, byteorder="little")
            buff = buff + val
        debugger.write_ap(2, 0x4, 0x0000a5a5)
        # write_ap(2, 0x0, 0x00000022)
        hexdump.hexdump((buff))
        return buff
        # print(buff)

    def parse_DAC(self ,buff):
        val2 = bytearray(buff).hex()
        print("-------------------------------------------------------------------------------")
        print("Parse Debug Auth Challenge:")
        print("-------------------------------------------------------------------------------")
        print("Version:", val2[:8])
        print("SOCC:", val2[8:16])
        print("UUID:", val2[16:48])
        print("ROTID_rkth_hash:", val2[56:120])
        print("CC_soc_pinned:", val2[120:128])
        print("CC_soc_default:", val2[128:136])
        print("Challenge:", val2[144:])
        time.sleep(2)

    def rsa_sign(self , buff):
        f_cert = open("dck_rsa_2048.dc", "rb")
        certificate = f_cert.read()
        val2 = bytearray(buff).hex()
        auth_beac = '00000000'
        auth_beacon = bytes.fromhex(auth_beac)
        # print(auth_beacon)
        #test_challenge = '680e5cd6ae32cd5b5e499d610620df538fe17e3f9f3013be5ffb1763666597f2'
        challenge = bytes.fromhex(val2[144:])

        # Create SHA256 of DC + Authbecon + Challenge and Sign using the DC private key
        print("-------------------------------------------------------------------------------")
        print("Create DIGEST of DC + Authbecon + Challenge and Sign using the DC private key:")
        print("-------------------------------------------------------------------------------")
        message = certificate + auth_beacon + challenge
        # print(message)
        f_private = open("dck_rsa_2048.pem", "rb")
        key = load_pem_private_key(f_private.read(), password=None, backend=default_backend())
        signature = key.sign(
            message,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        hexdump.hexdump(signature)
        time.sleep(2)
        # print("Signature:",len(signature), signature.hex() )
        # print("Signature:",len(signature), signature)
        return signature, auth_beacon



    def send_DAR(self, signature, auth_beac):

        f_cert = open("dck_rsa_2048.dc", "rb")
        certificate = f_cert.read()
        DAC = certificate + auth_beac + signature
        # print("Debug Auth Command Response <--",type(DAC),len(DAC),DAC)
        f = open("DAC1.txt", "w")
        f.write(DAC.hex())

        print("-------------------------------------------------------------------------------")
        print("Send Debug Authentication Response: DAR = Certificate + Authentication beacon + Signature ")
        print("-------------------------------------------------------------------------------")
        hexdump.hexdump(DAC)
        time.sleep(2)
        debugger.write_ap(2, 0x4, 0x00000011)
        val = debugger.read_ap(2, 0x8).to_bytes(4, byteorder="little")
        print("-------------------------------------------------------------------------------")
        print("Debug Auth Command Start Response <--", bytearray(val).hex())
        print("-------------------------------------------------------------------------------")
        for i in range(0, 2600, 8):
            # time.sleep(0.05)
            f = open("DAC1.txt", "rb")
            offset = i
            f.seek(offset, 1)
            output = f.read(8)
            out1 = output.decode()
            out = convert.convert_hex(out1, 'big', 'little')
            if output == b'00000000':
                output1 = int(output, base=16)
                debugger.write_ap(2, 0x4, output1)
                print("Request -->", output)
                val = debugger.read_ap(2, 0x8).to_bytes(4, byteorder="little")
                hexdump.hexdump(val)
            else:
                out1 = output.decode()
                out = convert.convert_hex(out1, 'big', 'little')
                if len(out) <= 6:
                    N = 2
                    temp = '{:<08}'
                    res = temp.format(out)
                    res1 = int(res, base=16)
                    debugger.write_ap(2, 0x4, res1)
                    print("Request -->", res)
                    val = debugger.read_ap(2, 0x8).to_bytes(4, byteorder="little")
                    hexdump.hexdump(val)
                else:
                    out2 = int(out, base=16)
                    debugger.write_ap(2, 0x4, out2)
                    print("Request -->", out)
                    val = debugger.read_ap(2, 0x8).to_bytes(4, byteorder="little")
                    hexdump.hexdump(val)

        debugger.write_ap(2, 0x4, 0x00000004)
        val = debugger.read_ap(2, 0x8).to_bytes(4, byteorder="little")
        print("-------------------------------------------------------------------------------")
        print("Debug Auth Exit Command Response <--", bytearray(val).hex())
        print("-------------------------------------------------------------------------------")


print("-------------------------------------------------------------------------------")
print("Start LPC55S69 Debug Authentication Protocol")
print("-------------------------------------------------------------------------------")
print("Check the MCU Debug/Access port registers, Debug Port - IDR and Access Port -IDCODE")
print("-------------------------------------------------------------------------------")


#Call the debugger class
debugger = Debugger(device= '/dev/ttyACM0')
debugger.init()

# Call the Debug Authentication class
auth = Debug_Auth()

#Call the Misc class
convert = Misc()

#Read IDR register
print(f"DPIDR: {hex(debugger.read_dp(0))}")

# Power up debug domain
debugger.write_dp(4, 0x50000000)

#Write to the AP Abort Register (ABORT) to reset state

# Scan the SWD bus for AP
for i in range(3):
    print(f"AP {i} IDCODE: {hex(debugger.read_ap(i, 0xfc))}")


#LPC55S69 Debug Authentication
response =  auth.request_DAC()
auth.parse_DAC(response)
sign ,beac = auth.rsa_sign(response)
auth.send_DAR(sign, beac)

print("-------------------------------------------------------------------------------")
print("Check whether AHB is unlocked:")
print("-------------------------------------------------------------------------------")
for i in range(3):
    #print(read_dp(i, 0xFC))
    print(f"AP {i} IDR: {hex(debugger.read_ap(i, 0xfc))}")

print("-------------------------------------------------------------------------------")
print("Read few bytes of memory from Flash address 0x0 to check the device is unlocked successfully:")
print("-------------------------------------------------------------------------------")
debugger.write_ap(0, 0x0, 0x23000002)
buffer = b''
for i in range(0, 0xFF, 4):
    debugger.write_ap(0, 0x4, 0x00000000 + i)
    val = debugger.read_ap(0, 0xc).to_bytes(4, byteorder="little")
    buffer = buffer + val

hexdump.hexdump(buffer)

