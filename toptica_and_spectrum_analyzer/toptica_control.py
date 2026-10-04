from time import sleep

from toptica.lasersdk.client import Client, NetworkConnection
from toptica.lasersdk.client import UserLevel, Subscription, Timestamp, SubscriptionValue


# The following string is used to define the connection to the device. It can be either
# an IP address, a serial number or system label (when it is in the same subnet),
# or a DNS entry (e.g. 'dlcpro.example.com').
DLCPRO_CONNECTION = '172.16.109.105'


# This will create a new Client and connect to the device via Ethernet. The with-statement
# will automatically call Client.open() and Client.close() at the appropriate times (without
# it these methods have to be called explicitly).
with Client(NetworkConnection(DLCPRO_CONNECTION)) as client:
    print("=== Connected Device ===")
    print("This is a {} with serial number {}.\n".format(
        client.get('system-type'), client.get('serial-number')))

    