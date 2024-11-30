import argparse
import sys

from TCPFlowGenerator import TCPFlowGenerator
from UDPFlowGenerator import UDPFlowGenerator

def main():
    parser = argparse.ArgumentParser(description='TCP/UDP Flow Generator')
    parser.add_argument('-s', '--server', action='store_true', help='Run as server')
    parser.add_argument('-c', '--client', help='Server IP address to connect to')
    parser.add_argument('-p', '--port', type=int, default=5001, help='Port number')
    parser.add_argument('-u', '--udp', action='store_true', help='Use UDP instead of TCP')
    parser.add_argument('-t', '--time', type=int, help='Test duration in seconds')
    parser.add_argument('-n', '--size', type=str, help='Total size to transfer in MB')
    parser.add_argument('-l', '--packet-size', type=int, help='Packet size in bytes')
    parser.add_argument('-b', '--bandwidth', type=str, help='Bandwidth limit in bps')
    parser.add_argument('-i', '--interval', type=float, default=1.0, help='Statistics interval in seconds')
    parser.add_argument('-dpps', '--distributed_packets_per_second', type=str, help='Distributed packets per second')
    parser.add_argument('-dl', '--distributed_packet-size', type=str, help='Distributed packet size in bytes')
    parser.add_argument('-db', '--distributed_bandwidth', type=str, help='Distributed bandwidth limit in bps')
    parser.add_argument('-bri','--bandwidth_reset_interval', type=float, help='Bandwidth reset interval in seconds')
    parser.add_argument('-J', '--json', action='store_true', help='Print statistics as JSON file')
    parser.add_argument('-1', '--one_test', action='store_true', help='Run only one test')

    args = parser.parse_args()

    if args.time is not None and args.size is not None:
        print("Error: Cannot specify both time and size")
        sys.exit(1)
    if args.time is None and args.size is None and not args.server:
        print("Error: Must specify either time or size")
        sys.exit(1)
    if args.server is None and args.client is None:
        print("Error: Must specify either server or client")
        sys.exit(1)
    if args.server and args.client:
        print("Error: Cannot specify both server and client")
        sys.exit(1)

    # 选择Generator类
    GeneratorClass = UDPFlowGenerator if args.udp else TCPFlowGenerator
    if args.server:
        generator = GeneratorClass('0.0.0.0', args.port, "server", args.time, args.size, 
                               args.packet_size, args.bandwidth, args.interval,
                               args.distributed_packets_per_second, args.distributed_packet_size,
                               args.distributed_bandwidth, args.bandwidth_reset_interval,
                               args.json, args.one_test)
        generator.run_server()
    elif args.client:
        generator = GeneratorClass(args.client, args.port, "client", args.time, args.size,
                               args.packet_size, args.bandwidth, args.interval,
                               args.distributed_packets_per_second, args.distributed_packet_size,
                               args.distributed_bandwidth, args.bandwidth_reset_interval,
                               args.json, args.one_test)
        generator.run_client()
    else:
        parser.print_help()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)