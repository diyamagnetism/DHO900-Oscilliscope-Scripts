import opcua

client = opcua.Client("opc.tcp://192.168.0.1:4840")  # your server URL



def browse(node, depth=0):
    for child in node.get_children():
        name = child.get_browse_name().Name
        cls = child.get_node_class().name
        print("  " * depth + f"{name} [{cls}] {child.nodeid}")
        browse(child, depth + 1)

try:
    print(client)
    client.connect()
    browse(client.get_objects_node())
finally:
    client.disconnect()