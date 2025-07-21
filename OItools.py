import sys
import subprocess
import os
import time
import json
import re
import resource
import signal
import threading
from datetime import datetime


class OItools:
    def __init__(self):
        # 获取当前时间
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.template = \
f'''//Author: Alencryenfo
//Date: {current_time}
#include <iostream>

using namespace std;

using ll = long long;
using ull = unsigned long long;

signed main() {{
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    cout.tie(nullptr);
    
    
    return 0;
}}
/*
{{
"C++版本":"C++23",
"优化等级":"-O2",
"时间限制":2000,
"内存限制":256,
"精准匹配":false,
"样例数目":1,
}}
1:
<<X

>>X

*/'''

    def ApplyTemplate(self, filename):
        """生成竞赛模板"""
        with open(filename, 'a') as f:
            f.write(self.template)
        print(f"✅ 模板已加载: {filename}")

    def Getonfig(self, File):
        """从文件中获取配置和样例"""
        with open(File, 'r', encoding='utf-8') as f:
            content = f.read()
        try:
            Content = list(re.finditer(r'/\*\s*(.*?)\s*\*/', content, re.DOTALL))[-1].group(1)
            JsonContent = re.sub(r',\s*}', '}', list(re.finditer(r'\{.*?\}', Content, re.DOTALL))[-1].group(0))
            Config = json.loads(JsonContent)
            if(Config.get("样例数目", 0) == 0):
                return Config, []
            else:
                json_end_pos = list(re.finditer(r'\{.*?\}', Content, re.DOTALL))[-1].end()
                SampleContent = Content[json_end_pos:]
                Samples = []
                SampleBlocks = re.split(r'(\d+):', SampleContent)[1:]  # 去掉第一个空元素
                for i in range(0, len(SampleBlocks), 2):
                    if i + 1 >= len(SampleBlocks):
                        break
                    Num = int(SampleBlocks[i])
                    Content = SampleBlocks[i + 1]
                    Match = re.search(r'<<(\d+)\s*(.*?)\s*>>(\d+)\s*(.*)', Content, re.DOTALL)
                    if not Match:
                        continue

                    InputCount = int(Match.group(1))
                    InputSection = Match.group(2)
                    OutputCount = int(Match.group(3))
                    OutputSection = Match.group(4)
                    InputLines = InputSection.splitlines(keepends=True)
                    # 如果行数不足，用空行（"\n"）补齐
                    if len(InputLines) < InputCount:
                        InputLines += ["\n"] * (InputCount - len(InputLines))
                    # 只取前 InputCount 行
                    InputLines = InputLines[:InputCount]
                    # 把它拼回一个整体字符串
                    InputData  = "".join(InputLines)

                    RawOutput   = OutputSection + "\n" * OutputCount
                    OutputLines = RawOutput.splitlines(keepends=True)[:OutputCount]
                    OutputList  = OutputLines[:OutputCount]
                    Samples.append({
                        'Num': Num,
                        'Input': InputData,
                        'Output': OutputList
                    })
                Samples.sort(key=lambda x: x['Num'])
                return Config, Samples
        except Exception as e:
            print(f"❌ 解析配置或样例失败: {e}\n自动尝试手动输入模式")
            return None, []

    def Check(self, OutList, AnsList, Config):
        """比较输出结果"""

        # 如果行数不一致，直接判为不通过
        if len(OutList) != len(AnsList):
            return False

        if Config["精准匹配"]:
            # 精准匹配：每行完全一致，包括中间/开头/末尾所有空白
            for a_line, e_line in zip(OutList, AnsList):
                if a_line != e_line:
                    return False
            return True
        else:
            # 非精准匹配：忽略每行末尾的空格和空行差异
            for a_line, e_line in zip(OutList, AnsList):
                if a_line.rstrip() != e_line.rstrip():
                    return False
            return True

    def AutoTest(self, ResFile, Sample, Config):
        """运行单个样例测试，监控 RSS & VSZ"""
        Num          = Sample['Num']
        InputText    = Sample['Input']
        ExpectedList = Sample['Output']       # list[str]
        TimeLimit    = Config["时间限制"] / 1000.0
        MemoryLimit  = Config["内存限制"] * 1024 * 1024  # 字节

        MaxRss      = 0
        MaxVsz      = 0
        MemExceeded = False
        StatusPath  = None

        def SetCpuLimit():
            resource.setrlimit(resource.RLIMIT_CPU,
                               (int(TimeLimit), int(TimeLimit)))

        def SampleStatus():
            """同步读取一次 /proc/<pid>/status"""
            nonlocal MaxRss, MaxVsz
            try:
                with open(StatusPath) as F:
                    for Line in F:
                        if Line.startswith("VmRSS:"):
                            Rss = int(Line.split()[1]) * 1024
                            MaxRss = max(MaxRss, Rss)
                        elif Line.startswith("VmSize:"):
                            Vsz = int(Line.split()[1]) * 1024
                            MaxVsz = max(MaxVsz, Vsz)
            except Exception:
                pass

        def MonitorMemory(Process):
            nonlocal MaxRss, MaxVsz, MemExceeded
            while Process.poll() is None:
                SampleStatus()
                if MaxRss > MemoryLimit or MaxVsz > MemoryLimit:
                    MemExceeded = True
                    Process.kill()
                    break
                time.sleep(0.01)

        # 启动子进程
        Process = subprocess.Popen(
            [f"{ResFile}"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=SetCpuLimit
        )

        # 设置 StatusPath 并立即取一次样
        StatusPath = f"/proc/{Process.pid}/status"
        SampleStatus()

        # 启动监控线程
        MonitorThread = threading.Thread(
            target=MonitorMemory, args=(Process,), daemon=True
        )
        MonitorThread.start()

        # 运行 & 读取输出
        StartTime = time.perf_counter()
        try:
            Stdout, Stderr = Process.communicate(input=InputText, timeout=TimeLimit)
        except subprocess.TimeoutExpired:
            Process.kill()
            Stdout, Stderr = Process.communicate()
            print(f"❌⏰ 样例 {Num} 超时（>{TimeLimit*1000:.0f}ms）")
            return False
        MonitorThread.join()
        if MaxRss > MemoryLimit or MaxVsz > MemoryLimit:
            MemExceeded = True
        ElapsedMs = (time.perf_counter() - StartTime) * 1000
        ActualList = Stdout.splitlines(keepends=True)
        Passed     = self.Check(ActualList, ExpectedList, Config)

        # 输出结果分类
        if MemExceeded:
            print(f"❌💾 样例 {Num} 超出内存限制（>{MemoryLimit//1024//1024}MB）")
        elif Process.returncode != 0:
            print(f"❌💥 样例 {Num} 异常退出，返回码: {Process.returncode}")
        else:
            if not Passed:
                print(f"❌ 样例 {Num} 输出不匹配")
                print("—— 期望输出 ——")
                for L in ExpectedList:
                    print(L, end="")
                print("\n—— 实际输出 ——")
                for L in ActualList:
                    print(L, end="")
                print("————————————")
            else:
                print(f"✅ 样例 {Num} 通过测试")

        if Stderr:
            print("—— 错误输出 ——")
            print(Stderr, end="")

        # 最后打印耗时和内存峰值
        print(
            f"⏱️ 运行时间: {ElapsedMs:.2f}ms    "
            f"💾 峰值内存: {MaxVsz/1024/1024:.2f}MB  "
        )
        return (not MemExceeded) and (Process.returncode == 0) and Passed


    def ManualTest(self, ResFile, TestNum,Config):
        """运行手动测试"""
        print(f"📝 手动测试 {TestNum}:")
        print("请输入数据行数:")
        DataLines = int(input())
        print(f"请输入 {DataLines} 行测试数据:")
        InputData = []
        for i in range(DataLines):
            line = input()
            InputData.append(line)
        InputText = '\n'.join(InputData)
        TimeLimit = Config["时间限制"] / 1000.0
        MemoryLimit = Config["内存限制"] * 1024 * 1024  # 转换为字节
        def SetLimits():
            resource.setrlimit(resource.RLIMIT_AS, (MemoryLimit, MemoryLimit))
            resource.setrlimit(resource.RLIMIT_CPU, (int(TimeLimit), int(TimeLimit)))
        StartTime = time.perf_counter()
        try:
            Result = subprocess.run(
                [f"{ResFile}"],
                input=InputText,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=TimeLimit,
                preexec_fn=SetLimits
            )
        except subprocess.TimeoutExpired:
            print(f"⏰ 程序运行超时（>{TimeLimit*1000:.0f}ms）")
            return False
        Elapsed = (time.perf_counter() - StartTime) * 1000
        Usage    = resource.getrusage(resource.RUSAGE_CHILDREN)
        MaxMemory = Usage.ru_maxrss * 1024
        if Result.returncode != 0:
            if Result.returncode < 0 and -Result.returncode == signal.SIGSEGV:
                print(f"💾 程序超出内存限制（>{MemoryLimit/(1024*1024):.0f}MB）")
            else:
                print(f"💥 程序异常退出，返回码: {Result.returncode}")
            print(f"⏱️ 运行时间: {Elapsed:.2f}ms")
            print(f"💾 峰值内存使用: {MaxMemory/(1024*1024):.2f}MB")
            return False
        if Result.stdout:
            print("标准输出:\n"+Result.stdout, end="")
        if Result.stderr:
            print("错误输出:\n"+Result.stderr, end="")
        print(f"⏱️ 运行时间: {Elapsed:.2f}ms    💾 峰值内存: {MaxMemory/(1024*1024):.2f}MB\n")
        return True

    def Test(self, File):
        """编译并运行测试"""
        print(f"🔧 加载文件: {File}")
        if not os.path.exists(File):
            print(f"❌ 文件不存在: {File}")
            return
        Config, Samples = self.Getonfig(File)
        if Config is None:
            print("❌ 无法解析配置，自动尝试默认模式\nC++版本: C++17\n优化等级: -O2\n时间限制: 2000ms\n内存限制: 256MB")
            Config = {"样例数目": 0, "精准匹配": False, "C++版本": "C++17", "优化等级": "-O2", "时间限制": 2000, "内存限制": 256}
            Samples = []

        print(f"🔧 编译文件: {File}")
        Resfile = File.replace('.cpp', '')+ '.app'
        # 根据配置构建编译命令
        CompileCMD = ['g++', '-o', Resfile, File]
        CompileCMD.append(f'-std={Config.get("C++版本", "C++17").lower().replace("c++", "c++")}')

        # 添加优化等级参数
        Opt = Config.get("优化等级", "-O2")
        if Opt and Opt.startswith('-O'):
            CompileCMD.append(Opt)

        result = subprocess.run(CompileCMD, capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ 编译失败:")
            if result.stdout.strip():
                print(result.stdout)
            if result.stderr.strip():
                print(result.stderr)
            try:
                os.remove(Resfile)
            except Exception as e:
                pass
            finally:
                print("已清理编译生成的文件")
            return

        print("✅ 编译成功!")

        if len(Samples) == 0:
            # 完全手动模式
            print("🔄 开始手动样例测试")
            TestNum = 1
            while True:
                self.ManualTest(Resfile, TestNum,Config)
                TestNum += 1
                order = input("\n是否继续测试? (y/n): ")
                if order.lower() != 'y':
                    break
        else:
            print("🔄 开始自动样例测试\n")
            PassedCount    = 0
            TotalSamples   = len(Samples)
            for S in Samples:
                if self.AutoTest(Resfile, S, Config):
                    PassedCount += 1
            print(f"✅ 自动测试完成：{PassedCount}/{TotalSamples} 通过")
        try:
            os.remove(Resfile)
        except Exception as e:
            pass
        finally:
            print("已清理编译生成的文件")
        return

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 oi_helper.py Template [FilePath]    # 生成模板")
        print("  python3 oi_helper.py Test [FilePath]        # 运行测试")
        return

    Obj= OItools()
    command = sys.argv[1]

    if command == "Template":
        FilePath = sys.argv[2]
        Obj.ApplyTemplate(FilePath)
    elif command == "Test":
        FilePath = sys.argv[2]
        Obj.Test(FilePath)
    else:
        print(f"❌ 未知命令: {command}")

if __name__ == "__main__":
    main()