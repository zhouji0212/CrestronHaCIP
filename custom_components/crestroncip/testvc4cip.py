import logging
import time
import crestroncipsync

# uncomment the line below to enable debugging output to console
logging.basicConfig(level=logging.DEBUG,
                    format="[%(levelname)s] (%(threadName)-10s) %(message)s")

# set up the client to connect to hostname "processor" at IP-ID 0x0A
cip = crestroncipsync.CIPSocketClient("127.0.0.1", 0x03)

# initiate the socket connection and start worker threads
cip.start()
time.sleep(1.5)

# you can force this client and the processor to resync using an update request
cip.update_request()  # note that this also occurs automatically on first connection

# for joins coming from this client going to the processor
cip.set("d", 1, 1)  # set digital join 1 high
cip.set("d", 13, 0)  # set digital join 132 low
cip.set("a", 12, 32456)  # set analog join 12 to 32456
# set serial join 101 to "Hello Crestron!"
cip.set("s", 10, "Hello Crestron!")
# pulses digital join 2 (sets it high then immediately sets it low again)
cip.pulse(2)
# emulates a touchpanel button press on digital join 3 (stays high until released)
cip.press(3)
cip.release(3)  # emulates a touchpanel button release on digital join 3

# for joins coming from the processor going to this client
digital_34 = cip.get("d", 3)  # returns the current state of digital join 34
analog_109 = cip.get("a", 10)  # returns the current state of analog join 109
serial_223 = cip.get("s", 10)  # returns the current state of serial join 223

# you should really subscribe to incoming (processor > client) joins rather than polling


def my_callback(sigtype, join, state):
    print(f"{sigtype} {join} : {state}")


# run 'my_callback` when digital join 1 changes
cip.subscribe("d", 1, my_callback)

# this will close the socket connection when you're finished
cip.stop()
