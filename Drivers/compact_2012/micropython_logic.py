
import pyb
import micropython
import binascii
import utime

'''
compact_40_pin_flatcable	pyboard

compact_40_pin_03	pyboard_gnd
compact_40_pin_07	pyboard_gnd
compact_40_pin_11	pyboard_gnd

compact_40_pin_4	pyboard_X6	SCK
compact_40_pin_8	pyboard_X7	MISO
compact_40_pin_12	pyboard_X8	MOSI

compact_40_pin_13	pyboard_X10	(DIO(0))
compact_40_pin_17	pyboard_Y1	(DIO(1))
compact_40_pin_19	pyboard_Y2	(DIO(2))
compact_40_pin_23	pyboard_Y3	(DIO(3))
compact_40_pin_27	pyboard_Y4	(DIO(4))
compact_40_pin_31	pyboard_Y5	(DIO(5))
compact_40_pin_33	pyboard_Y6	(DIO(6))
compact_40_pin_35	pyboard_Y7	(DIO(7))

compact_40_pin_16	pyboard_X11	(CS(0))
compact_40_pin_22	pyboard_X12	(CS(1))
'''

# Initialize DAC20 every x seconds
INITIALIZATION_INTERVAL_MS = 5000
time_next_initialization_ms = utime.ticks_ms()

# The blinking of the LEDS
# The geophone will be read every 1/BLINK_FREQUENCY_HZ
BLINK_FREQUENCY_HZ=2

COMMUNICATION_BLUE_LED_INTERVAL_MS = 2000
time_next_communication_blue_led_ms = utime.ticks_ms()
b_led_blue_is_blinking = False
b_led_toggle_on = False

b_error = False
i_geophone_dac = 0
i_geophone_threshold_dac = 4096

p_LINE_LDAC_out = pyb.Pin(pyb.Pin.board.Y2, pyb.Pin.IN)
p_LINE_SYNC_out = pyb.Pin(pyb.Pin.board.X10, pyb.Pin.OUT_PP)
p_CHIPSELECT_AD5791_out = pyb.Pin(pyb.Pin.board.X11, pyb.Pin.OUT_PP)
p_CHIPSELECT_AD5300_out = pyb.Pin(pyb.Pin.board.Y3, pyb.Pin.OUT_PP)
p_CHIPSELECT_GEO_MCP3201_out = pyb.Pin(pyb.Pin.board.X12, pyb.Pin.OUT_PP)
p_LED_RED_out = pyb.Pin(pyb.Pin.board.Y5, pyb.Pin.OUT_PP)
p_LED_GREEN_out = pyb.Pin(pyb.Pin.board.Y6, pyb.Pin.OUT_PP)
p_LED_BLUE_out = pyb.Pin(pyb.Pin.board.Y7, pyb.Pin.OUT_PP)

def pyboard_init():
    p_LINE_SYNC_out.value(0)
    p_CHIPSELECT_AD5791_out.value(1)
    p_CHIPSELECT_AD5300_out.value(1)
    p_CHIPSELECT_GEO_MCP3201_out.value(1)
    p_LED_RED_out.value(0)
    p_LED_GREEN_out.value(0)
    p_LED_BLUE_out.value(0)


'''
        pyboard_init output (using settings from VI)
        23: 0 0:write 1:read 
        22: 0 (Control Reg) 
        21: 1 (Control Reg) 
        20: 0 (Control Reg) 
        19: 0 Reserved
        18: 0 Reserved
        17: 0 Reserved
        16: 0 Reserved
        15: 0 Reserved
        14: 0 Reserved
        13: 0 Reserved
        12: 0 Reserved
        11: 0 Reserved
        10: 0 Reserved
        9: 0 LIN COMP
        8: 0 LIN COMP
        7: 0 LIN COMP
        6: 0 LIN COMP
        5: 0 SDODIS
        4: 1 BIN/2sC
        3: 0 DACTRI
        2: 0 OPGND
        1: 1 RBUF
        0: 0 Reserved
'''
bytearray_initialization = bytearray([0b00100000, 0b00000000, 0b00010010]*10)
assert len(bytearray_initialization) == 30


def communication_activity():
    global b_led_blue_is_blinking
    b_led_blue_is_blinking = True
    global time_next_communication_blue_led_ms
    time_next_communication_blue_led_ms = utime.ticks_add(utime.ticks_ms(), COMMUNICATION_BLUE_LED_INTERVAL_MS)

def set_dac(str_dac28):
    set_dac_nibbles(str_dac28)

    # http://docs.micropython.org/en/latest/library/pyb.SPI.html

    # DAC20
    __spi_initialize_DAC20()

    # DAC20
    __spi_write_DAC20()

    # DAC8
    __spi_write_DAC8()

    communication_activity()

    return get_status()

def __spi_initialize_DAC20():
    p_CHIPSELECT_AD5791_out.value(0)
    p_LINE_SYNC_out.value(0)
    spi.send_recv(bytearray_initialization, timeout=100)
    p_LINE_SYNC_out.value(1)
    p_CHIPSELECT_AD5791_out.value(1)

def __spi_write_DAC20():
    p_CHIPSELECT_AD5791_out.value(0)
    p_LINE_SYNC_out.value(0)
    spi.send_recv(binascii.unhexlify(dac20_nibbles), timeout=100)
    p_LINE_SYNC_out.value(1)

    p_LINE_LDAC_out.init(mode=pyb.Pin.OUT_PP)
    p_LINE_LDAC_out.value(0)

    p_LINE_LDAC_out.value(1)
    p_LINE_LDAC_out.init(mode=pyb.Pin.IN)
    p_CHIPSELECT_AD5791_out.value(1)

def __spi_write_DAC8():
    p_LINE_SYNC_out.value(0)
    p_CHIPSELECT_AD5791_out.value(0)

    dac8_bytes_value1to9, dac8_bytes_value10 = splice_dac8()

    # Shift the first 9 values through the DAC20
    spi.send_recv(dac8_bytes_value1to9, timeout=100)

    p_CHIPSELECT_AD5300_out.value(0)
    # Now shift the last value and enable the DAC8 chip select
    # So, all DAC8 will take the value
    spi.send_recv(dac8_bytes_value10, timeout=100)
    p_CHIPSELECT_AD5300_out.value(1)

    p_CHIPSELECT_AD5791_out.value(1)
    p_LINE_SYNC_out.value(1)

def __spi_read_geophone():
    # http://ww1.microchip.com/downloads/en/devicedoc/21290d.pdf
    p_CHIPSELECT_GEO_MCP3201_out.value(0)

    # ask for two bytes by first sending two bytes
    # This buffer is initialized with (0, 0) and also serves to return the result
    read_geophone = bytearray(2)
    spi.send_recv(read_geophone, read_geophone, timeout=100)
    p_CHIPSELECT_GEO_MCP3201_out.value(1)

    global i_geophone_dac
    i_geophone_dac = read_geophone[1] + 256*read_geophone[0]
    # shift one bit and filter out 12 bits of data
    i_geophone_dac >>= 1
    # Filter 12 bits: the MCP3201 has 12 bit resolution
    i_geophone_dac &= 0xFFF

def get_status():
    return b_error, i_geophone_dac

def set_geophone_threshold_dac(i_threshold_dac):
    global i_geophone_threshold_dac
    i_geophone_threshold_dac = i_threshold_dac

def set_user_led(on):
    assert isinstance(on, bool)
    p_LED_GREEN_out.value(on)

pyboard_init()

micropython.alloc_emergency_exception_buf(100)
timer_blink = pyb.Timer(4, freq=BLINK_FREQUENCY_HZ)

# The LED on the pyboard
pyb_led_red = pyb.LED(1)
pyb_led_red.on()

spi = pyb.SPI(1)

# 600000: 300000
# 1200000: 650000
# 2000000: 1300000
# 1312500: 1312500
spi.init(pyb.SPI.MASTER, baudrate=1312500, polarity=0, phase=1, crc=None)

__spi_initialize_DAC20()
__spi_read_geophone()

def blink(__dummy__):
    # The geophone will be red all 1/BLINK_FREQUENCY_HZ (500ms)
    __spi_read_geophone()

    global time_next_initialization_ms
    i_wait_ms = utime.ticks_diff(time_next_initialization_ms, utime.ticks_ms())
    if i_wait_ms < 0:
        time_next_initialization_ms = utime.ticks_add(utime.ticks_ms(), INITIALIZATION_INTERVAL_MS)
        __spi_initialize_DAC20()

    global b_led_blue_is_blinking
    i_wait_ms = utime.ticks_diff(time_next_communication_blue_led_ms, utime.ticks_ms())
    if i_wait_ms < 0:
        # Switch the blue led off, if now communication was detected during the last period
        b_led_blue_is_blinking = False

    pyb_led_red.toggle()
    global b_led_toggle_on
    b_led_toggle_on = not b_led_toggle_on

    b_led_red_on = i_geophone_dac >= i_geophone_threshold_dac
    p_LED_RED_out.value(b_led_red_on)
    p_LED_BLUE_out.value(b_led_toggle_on and b_led_blue_is_blinking)

timer_blink.callback(lambda timer: micropython.schedule(blink, None))