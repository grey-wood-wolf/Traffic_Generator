# Traffic_Generator

Traffic_Generator 是一个高性能的网络流量生成和测试工具，支持 TCP 和 UDP 协议。该工具专为网络性能测试、网络设备评估和协议分析而设计，具有强大的统计分布控制能力。

## 主要特性

- **多协议支持**: 支持 TCP 和 UDP 协议的流量生成
- **双模式运行**: 可配置为服务器或客户端模式
- **IPv4/IPv6支持**: 原生支持 IPv4 和 IPv6 网络
- **统计分布控制**: 支持指数分布的包间隔、包大小和带宽变化
- **实时统计**: 提供详细的网络性能指标监控
- **时钟同步**: UDP模式下支持高精度时延测量（通过chrony/NTP同步）
- **数据处理**: 包含UDP转发器工具，支持数据包修改和转发

## 架构概述

项目采用模块化设计：
- `FlowGenerator.py`: 基础流量生成器类
- `TCPFlowGenerator.py`: TCP专用流量生成器
- `UDPFlowGenerator.py`: UDP专用流量生成器
- `main.py`: 命令行接口和参数解析
- `forwarder/udp_forwarder.py`: UDP数据包转发和处理工具
- `config.json`: 配置文件

## 参数详解

### 基础参数
- `-s`, `--server`: 以服务器模式运行，监听指定端口等待连接
- `-c`, `--client <IP>`: 以客户端模式运行，连接到指定的服务器IP地址
- `-p`, `--port <NUM>`: 服务器端口号（默认：5001）
- `-u`, `--udp`: 使用UDP协议（默认为TCP）

### 测试控制参数
- `-t`, `--time <SEC>`: 测试持续时间（秒）
- `-n`, `--size <SIZE>`: 传输总数据量（支持K/M/G后缀，如"1G"）
- `-l`, `--packet-size <BYTES>`: 数据包大小（字节）
- `-b`, `--bandwidth <RATE>`: 带宽限制（支持K/M/G后缀，如"100M"表示100Mbps）

### 统计分布参数
- `-dpps`, `--distributed_packets_per_second <DIST>`: 包间隔分布模式（exp=指数分布）
- `-dl`, `--distributed_packet-size <DIST>`: 包大小分布模式（exp=指数分布）
- `-db`, `--distributed_bandwidth <DIST>`: 带宽分布模式（exp=指数分布）
- `-bri`, `--bandwidth_reset_interval <SEC>`: 带宽重置间隔（秒）

### 输出和控制参数
- `-i`, `--interval <SEC>`: 统计显示间隔（默认：1.0秒）
- `-J`, `--json`: 以JSON格式输出统计数据
- `-1`, `--one_test`: 只运行一次测试后退出
- `-B`, `--bind_address <IP>`: 服务器绑定地址
- `-6`, `--ipv6`: 使用IPv6协议
- `-ppkg`, `--printpkg`: 打印数据包内容（仅UDP支持）
- `-v`, `--version`: 显示版本信息

## 使用示例

### 基础TCP测试
```bash
# 服务器端
python3 main.py -s -p 5001 -B 192.168.1.100

# 客户端
python3 main.py -c 192.168.1.100 -p 5001 -t 10 -b 1G
```

### UDP性能测试
```bash
# 服务器端
python3 main.py -s -p 5001 -u -B 192.168.1.100 -J

# 客户端
python3 main.py -c 192.168.1.100 -p 5001 -u -n 1G -b 100M -l 1450 -J
```

### 高级分布控制测试
```bash
# 指数分布的包间隔、包大小和带宽
python3 main.py -c 192.168.1.100 -u -n 1G -b 100M -l 1450 \
  -dpps exp -dl exp -db exp -bri 1 -J
```

### IPv6测试
```bash
# 服务器端
python3 main.py -s -6 -B 2001:db8::1 -u

# 客户端
python3 main.py -c 2001:db8::1 -6 -u -t 30 -b 500M
```

## 性能指标

该工具提供丰富的网络性能指标：

### TCP模式
- **带宽和数据速率**: 实时带宽利用率和有效数据传输速率
- **拥塞窗口(CWND)**: TCP拥塞控制窗口大小监控
- **往返时延(RTT)**: 网络往返时延测量
- **重传统计**: 数据包重传次数统计

### UDP模式
- **时延和抖动**: 高精度时延测量和抖动计算
- **丢包统计**: 详细的丢包率和丢包数统计
- **时钟同步**: 基于chrony(Linux)/NTP(Windows)的时钟偏移修正

## UDP转发器

项目包含一个功能强大的UDP转发器(`forwarder/udp_forwarder.py`)，支持：

- **IPv4/IPv6双向转发**: 自动处理IPv4和IPv6之间的协议转换
- **数据包修改**: 可配置的数据包内容截取和自定义内容插入
- **TCP转发**: 基于socat的TCP协议转发功能

### 转发器使用示例
```bash
python3 forwarder/udp_forwarder.py \
  --ipv4_addr 192.168.1.100 --ipv4_port 5001 \
  --ipv6_addr 2001:db8::100 --ipv6_port 5001 \
  --reserve_rate 0.7 --new_rate 0.2 --new_content "-test-"
```

## 依赖要求

- Python 3.6+
- numpy
- Linux系统建议安装chrony用于时钟同步
- Windows系统建议配置NTP服务

## 配置文件

`config.json`支持以下配置：
```json
{
    "offset_fix_rate": 5
}
```

## 性能限制

由于采用纯Python实现（未使用DPDK技术），性能上限为：
- **TCP**: 约500Mbps
- **UDP**: 约8Gbps

## 注意事项

1. **时钟同步**: 进行时延测试时，务必确保客户端和服务器的系统时钟已同步
2. **防火墙**: 确保测试端口未被防火墙阻挡
3. **权限**: 某些高性能配置可能需要管理员权限
4. **网络环境**: 建议在隔离的测试网络中进行高速流量测试

## 版本信息

当前版本: Klonetpktgen 1.2.0

## 许可证

本项目采用开源许可证，详细信息请参考项目许可证文件。