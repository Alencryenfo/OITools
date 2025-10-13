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
        CurrentTime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.Template = \
f'''//Author: Alencryenfo
//Date: {CurrentTime}
#include <iostream>

using namespace std;

using ll = long long;
using ull = unsigned long long;
using pii = pair<int, int>;

void solve(){{

    return ;
}}

signed main() {{
#ifdef DEBUG
    freopen("test.in", "r", stdin);
    freopen("test.out", "w", stdout);
#endif

    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    cout.tie(nullptr);

    int T;
    cin >> T;
    while(T--){{
        solve();
    }}
    return 0;
}}
/*
{{
"C++版本":"C++23",
"优化等级":"-O2",
"时间限制":2000,
"内存限制":256,
"自动测试":1,
}}
<<

>>

*/'''

    def ApplyTemplate(self, FileName):
        """生成竞赛模板"""
        with open(FileName, 'a') as F:
            F.write(self.Template)
        print(f"✅ 模板已加载: {FileName}")

    def Getonfig(self, File):
        """从文件中获取配置和样例"""
        with open(File, 'r', encoding='utf-8') as f:
            content = f.read()
        try:
            Content = list(re.finditer(r'/\*\s*(.*?)\s*\*/', content, re.DOTALL))[-1].group(1)
            JsonContent = re.sub(r',\s*}', '}', list(re.finditer(r'\{.*?\}', Content, re.DOTALL))[-1].group(0))
            Config = json.loads(JsonContent)
            if(Config.get("自动测试", 0) == 0):
                return Config, []
            else:
                json_end_pos = list(re.finditer(r'\{.*?\}', Content, re.DOTALL))[-1].end()
                SampleContent = Content[json_end_pos:]
                Samples = []
                
                # 新格式：查找所有<<...>>...<<...>>模式
                SampleMatches = re.finditer(r'<<(\d+)\s*(.*?)\s*>>(\d+)\s*(.*?)(?=<<|\Z)', SampleContent, re.DOTALL)
                SampleNum = 1
                
                for Match in SampleMatches:
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
                    InputData = "".join(InputLines)

                    RawOutput = OutputSection + "\n" * OutputCount
                    OutputLines = RawOutput.splitlines(keepends=True)[:OutputCount]
                    OutputList = OutputLines[:OutputCount]
                    
                    Samples.append({
                        'Num': SampleNum,
                        'Input': InputData,
                        'Output': OutputList
                    })
                    SampleNum += 1
                    
                # 如果解析失败或没有样例，自动转为手动测试
                if not Samples:
                    print("⚠️ 样例格式不合法，自动转为手动测试")
                    Config["自动测试"] = 0
                    return Config, []
                    
                return Config, Samples
        except Exception as e:
            print(f"❌ 解析配置或样例失败: {e}\n自动尝试手动输入模式")
            return None, []

    def Check(self, OutList, AnsList, Config):
        """比较输出结果 - 忽略每行末尾的空格差异"""

        # 如果行数不一致，直接判为不通过
        if len(OutList) != len(AnsList):
            return False
        # 忽略每行末尾的空格和空行差异
        for a_line, e_line in zip(OutList, AnsList):
            if a_line.rstrip() != e_line.rstrip():
                return False
        return True

    def AutoTest(self, ResFile, Sample, Config):
        """使用文件I/O运行单个样例测试，符合OI评测标准"""
        Num = Sample['Num']
        InputText = Sample['Input']
        ExpectedList = Sample['Output']
        TimeLimit = Config["时间限制"] / 1000.0  # 转换为秒
        MemoryLimit = Config["内存限制"] * 1024 * 1024  # 转换为字节
        
        # 监控变量
        MaxMemory = 0
        MemExceeded = False
        TimeExceeded = False
        StatusPath = None
        
        def SetResourceLimits():
            """设置资源限制 - OI标准"""
            # 内存限制：虚拟内存和物理内存
            resource.setrlimit(resource.RLIMIT_AS, (MemoryLimit, MemoryLimit))
            resource.setrlimit(resource.RLIMIT_DATA, (MemoryLimit, MemoryLimit))
            # CPU时间限制 - 使用稍微宽松的限制避免误杀
            CpuTimeLimit = int(TimeLimit * 1.2)  
            resource.setrlimit(resource.RLIMIT_CPU, (CpuTimeLimit, CpuTimeLimit))
            
        def GetMemoryUsage():
            """获取当前内存使用情况"""
            nonlocal MaxMemory
            try:
                with open(StatusPath, 'r') as F:
                    Content = F.read()
                    VmSize = 0
                    VmRSS = 0
                    
                    # 同时检查VmSize（虚拟内存）和VmRSS（物理内存）
                    for Line in Content.splitlines():
                        if Line.startswith('VmSize:'):
                            VmSize = int(Line.split()[1]) * 1024  # kB转字节
                        elif Line.startswith('VmRSS:'):
                            VmRSS = int(Line.split()[1]) * 1024  # kB转字节
                    
                    # 使用VmSize和VmRSS中的较大值作为内存使用量
                    CurrentMem = max(VmSize, VmRSS)
                    MaxMemory = max(MaxMemory, CurrentMem)
                    return CurrentMem
            except (FileNotFoundError, ValueError, IndexError, ProcessLookupError):
                return 0
                
        def MonitorProcess(Process):
            """监控进程资源使用 - OI优化版本"""
            nonlocal MaxMemory, MemExceeded
            
            # 阶段1: 程序启动阶段 - 极密集监控内存分配
            StartupChecks = 50  # 增加检查次数
            for I in range(StartupChecks):
                if Process.poll() is not None:
                    break
                    
                CurrentMem = GetMemoryUsage()
                if CurrentMem > MemoryLimit:
                    MemExceeded = True
                    Process.terminate()  # 优先使用terminate而非kill
                    time.sleep(0.01)
                    if Process.poll() is None:
                        Process.kill()
                    return
                    
                time.sleep(0.001)  # 1ms间隔，更密集监控
            
            # 阶段2: 运行时监控 - 降低频率
            while Process.poll() is None:
                CurrentMem = GetMemoryUsage()
                if CurrentMem > MemoryLimit:
                    MemExceeded = True
                    Process.terminate()
                    time.sleep(0.01)
                    if Process.poll() is None:
                        Process.kill()
                    return
                    
                time.sleep(0.05)  # 50ms间隔，降低CPU占用
        
        # 准备测试文件
        try:
            with open("test.in", "w", encoding="utf-8") as F:
                F.write(InputText)
            with open("test.ans", "w", encoding="utf-8") as F:
                F.writelines(ExpectedList)
        except IOError as E:
            print(f"❌ 样例 {Num} 文件写入失败: {E}")
            return False
            
        # 启动被测程序
        StartTime = time.perf_counter()
        try:
            Process = subprocess.Popen(
                [os.path.abspath(ResFile)],
                stderr=subprocess.PIPE,
                stdout=subprocess.DEVNULL,  # 输出重定向到文件
                stdin=subprocess.DEVNULL,   # 输入来自文件
                text=True,
                preexec_fn=SetResourceLimits
            )
        except OSError as E:
            print(f"❌ 样例 {Num} 程序启动失败: {E}")
            self.CleanupTestFiles()
            return False
            
        StatusPath = f"/proc/{Process.pid}/status"
        
        # 启动监控线程
        MonitorThread = threading.Thread(
            target=MonitorProcess, args=(Process,), daemon=True
        )
        MonitorThread.start()
        
        # 等待程序完成 - 使用精确计时
        try:
            Stdout, Stderr = Process.communicate(timeout=TimeLimit)
        except subprocess.TimeoutExpired:
            TimeExceeded = True
            Process.terminate()
            time.sleep(0.01)
            if Process.poll() is None:
                Process.kill()
            try:
                Stdout, Stderr = Process.communicate(timeout=0.1)
            except subprocess.TimeoutExpired:
                Stdout, Stderr = "", "程序因超时被终止"
                
        # 停止监控
        MonitorThread.join(timeout=0.1)
        ElapsedTime = (time.perf_counter() - StartTime) * 1000  # 转换为毫秒
        
        # 获取程序输出
        ActualList = []
        try:
            with open("test.out", "r", encoding="utf-8") as F:
                ActualList = F.readlines()
        except FileNotFoundError:
            ActualList = []
        except UnicodeDecodeError:
            print(f"❌ 样例 {Num} 输出文件编码错误")
            self.CleanupTestFiles()
            return False
            
        # 判题逻辑
        Result = self.EvaluateResult(
            Num, Process.returncode, TimeExceeded, MemExceeded,
            ActualList, ExpectedList, Stderr, ElapsedTime, MaxMemory, Config
        )
        
        self.CleanupTestFiles()
        return Result

    def EvaluateResult(self, Num, ReturnCode, TimeExceeded, MemExceeded, 
                      ActualList, ExpectedList, Stderr, ElapsedTime, MaxMemory, Config):
        """统一的结果评估和输出逻辑 - OI标准"""
        MemoryLimitMB = Config["内存限制"]
        TimeLimitMS = Config["时间限制"]
        
        # 判断程序执行状态
        if TimeExceeded:
            print(f"❌⏰ 样例 {Num} 时间超限 (>{TimeLimitMS}ms)")
            print(f"⏱️ 时间: {ElapsedTime:.0f}ms / {TimeLimitMS}ms    "
                  f"💾 内存: {MaxMemory/1024/1024:.1f}MB / {MemoryLimitMB}MB")
            return False
        elif MemExceeded:
            print(f"❌💾 样例 {Num} 内存超限 (>{MemoryLimitMB}MB)")
            print(f"⏱️ 时间: {ElapsedTime:.0f}ms / {TimeLimitMS}ms    "
                  f"💾 内存: {MaxMemory/1024/1024:.1f}MB / {MemoryLimitMB}MB")
            return False
        elif ReturnCode != 0:
            if ReturnCode == -signal.SIGKILL:
                print(f"❌💾 样例 {Num} 被系统终止 (可能内存超限)")
            elif ReturnCode == -signal.SIGSEGV:
                print(f"❌💥 样例 {Num} 段错误 (访问违法内存)")
            elif ReturnCode == -signal.SIGFPE:
                print(f"❌ 样例 {Num} 浮点异常 (除零错误)")
            elif ReturnCode == -signal.SIGABRT:
                # 检查是否为内存分配失败导致的异常
                if MaxMemory / (1024 * 1024) > MemoryLimitMB * 0.8:  # 接近限制时认为是内存问题
                    print(f"❌💾 样例 {Num} 内存分配失败 (可能超限)")
                else:
                    print(f"❌💥 样例 {Num} 程序异常终止 (SIGABRT)")
            else:
                print(f"❌💥 样例 {Num} 运行时错误 (退出码: {ReturnCode})")
            
            # 显示性能信息
            print(f"⏱️ 时间: {ElapsedTime:.0f}ms / {TimeLimitMS}ms    "
                  f"💾 内存: {MaxMemory/1024/1024:.1f}MB / {MemoryLimitMB}MB")
            return False
        else:
            # 检查输出正确性
            Passed = self.Check(ActualList, ExpectedList, Config)
            if not Passed:
                print(f"❌ 样例 {Num} 答案错误")
                self.ShowDiff(ExpectedList, ActualList)
            else:
                print(f"✅ 样例 {Num} 通过")
                
            # 显示性能信息
            print(f"⏱️ 时间: {ElapsedTime:.0f}ms / {TimeLimitMS}ms    "
                  f"💾 内存: {MaxMemory/1024/1024:.1f}MB / {MemoryLimitMB}MB")
            
            # 显示调试信息（如果有）
            if Stderr and Stderr.strip():
                print("—— 调试信息 ——")
                print(Stderr.strip())
            
            return Passed

        # 对于运行时错误，也显示调试信息
        if Stderr and Stderr.strip():
            print("—— 调试信息 ——")
            print(Stderr.strip())
            
        return False

    def ShowDiff(self, ExpectedList, ActualList):
        """显示期望输出与实际输出的差异"""
        print("—— 期望输出 ——")
        for I, Line in enumerate(ExpectedList, 1):
            print(f"{I:2d}│{repr(Line)}")
        print("—— 实际输出 ——") 
        for I, Line in enumerate(ActualList, 1):
            print(f"{I:2d}│{repr(Line)}")
        print("—————————————")

    def ManualTest(self, ResFile, TestNum, Config):
        """使用文件I/O运行手动测试 - OI风格"""
        print(f"📝 手动测试 {TestNum}:")
        print("请输入测试数据行数:")
        try:
            DataLines = int(input())
        except ValueError:
            print("❌ 输入格式错误，请输入数字")
            return False
            
        print(f"请输入 {DataLines} 行测试数据:")
        InputData = []
        for I in range(DataLines):
            try:
                Line = input(f"第{I+1}行: ")
                InputData.append(Line)
            except (EOFError, KeyboardInterrupt):
                print("\n❌ 输入被中断")
                return False
                
        InputText = '\n'.join(InputData)
        if InputText and not InputText.endswith('\n'):
            InputText += '\n'
        
        TimeLimit = Config["时间限制"] / 1000.0
        MemoryLimit = Config["内存限制"] * 1024 * 1024

        def SetResourceLimits():
            """设置资源限制 - 与AutoTest保持一致"""
            resource.setrlimit(resource.RLIMIT_AS, (MemoryLimit, MemoryLimit))
            resource.setrlimit(resource.RLIMIT_DATA, (MemoryLimit, MemoryLimit))
            CpuTimeLimit = int(TimeLimit * 1.2)
            resource.setrlimit(resource.RLIMIT_CPU, (CpuTimeLimit, CpuTimeLimit))

        # 写入测试输入文件
        try:
            with open("test.in", "w", encoding="utf-8") as F:
                F.write(InputText)
        except IOError as E:
            print(f"❌ 无法写入测试文件: {E}")
            return False

        # 运行程序
        StartTime = time.perf_counter()
        try:
            Result = subprocess.run(
                [os.path.abspath(ResFile)],
                stderr=subprocess.PIPE,
                stdout=subprocess.DEVNULL,  # 输出重定向到文件
                stdin=subprocess.DEVNULL,   # 输入来自文件
                text=True,
                timeout=TimeLimit,
                preexec_fn=SetResourceLimits
            )
        except subprocess.TimeoutExpired:
            print(f"❌⏰ 程序运行超时 (>{Config['时间限制']}ms)")
            self.CleanupTestFiles()
            return False
        except OSError as E:
            print(f"❌ 程序启动失败: {E}")
            self.CleanupTestFiles()
            return False
            
        ElapsedTime = (time.perf_counter() - StartTime) * 1000
        
        # 获取内存使用信息（简化版本）
        Usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        MaxMemory = Usage.ru_maxrss * 1024  # Linux上是KB，转换为字节

        # 评估运行结果
        Success = self.EvaluateManualResult(
            TestNum, Result.returncode, ElapsedTime, MaxMemory, 
            Result.stderr, Config
        )
        
        self.CleanupTestFiles()
        return Success

    def EvaluateManualResult(self, TestNum, ReturnCode, ElapsedTime, MaxMemory, Stderr, Config):
        """评估手动测试结果"""
        TimeLimitMS = Config["时间限制"]
        MemoryLimitMB = Config["内存限制"]
        
        # 检查运行状态
        if ReturnCode != 0:
            if ReturnCode == -signal.SIGKILL:
                print(f"❌💀 测试 {TestNum} 被系统终止 (可能内存超限)")
            elif ReturnCode == -signal.SIGSEGV:
                print(f"❌💥 测试 {TestNum} 段错误 (访问违法内存)")
            elif ReturnCode == -signal.SIGFPE:
                print(f"❌🔢 测试 {TestNum} 浮点异常 (除零错误)")
            else:
                print(f"❌💥 测试 {TestNum} 运行时错误 (退出码: {ReturnCode})")
        else:
            print(f"✅ 测试 {TestNum} 程序正常结束")

        # 显示程序输出
        try:
            with open("test.out", "r", encoding="utf-8") as F:
                Output = F.read()
            if Output:
                print("—— 程序输出 ——")
                print(Output, end="" if Output.endswith('\n') else '\n')
            else:
                print("程序无输出")
        except FileNotFoundError:
            print("程序未产生输出文件")
        except UnicodeDecodeError:
            print("❌ 输出文件编码错误")

        # 显示调试信息
        if Stderr and Stderr.strip():
            print("—— 调试信息 ——")
            print(Stderr.strip())

        # 显示性能信息
        print(f"⏱️ 时间: {ElapsedTime:.0f}ms / {TimeLimitMS}ms    "
              f"💾 内存: {MaxMemory/1024/1024:.1f}MB / {MemoryLimitMB}MB")
        
        return ReturnCode == 0

    def CleanupTestFiles(self):
        """清理测试文件"""
        TestFiles = ["test.in", "test.out", "test.ans"]
        for FileName in TestFiles:
            try:
                os.remove(FileName)
            except FileNotFoundError:
                pass
    
    def MemorySafetyCheck(self, ExeFile, TestCount, Samples, Config):
        """使用调试版本进行内存安全检查"""
        MemoryLimit = Config["内存限制"]
        CheckCount = min(TestCount, 3)  # 最多检查前3个样例
        
        for I in range(CheckCount):
            Sample = Samples[I]
            SampleNum = Sample["Num"]
            
            # 创建测试输入文件
            with open("test.in", "w", encoding="utf-8") as F:
                F.write(Sample["Input"])
            
            # 执行程序并监控内存
            MemorySafe = self.AutoTest(ExeFile, Sample, Config, SafetyCheckMode=True)
            
            if not MemorySafe:
                print(f"⚠️ 样例 {SampleNum} 内存安全检查失败")
                return False
                
        print(f"✅ 已检查 {CheckCount} 个样例，内存使用安全")
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
            Config = {"自动测试": 0, "C++版本": "C++17", "优化等级": "-O2", "时间限制": 2000, "内存限制": 256}
            Samples = []

        print(f"🔧 编译文件: {File}")
        ResFile = File.replace('.cpp', '') + '.app'
        # 根据配置构建编译命令
        CompileCMD = ['g++', '-o', ResFile, File]
        CompileCMD.append(f'-std={Config.get("C++版本", "C++17").lower().replace("c++", "c++")}')
        
        # 添加DEBUG宏定义
        CompileCMD.append('-DDEBUG')

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
                os.remove(ResFile)
            except Exception as e:
                pass
            finally:
                print("已清理编译生成的文件")
            return

        print("✅ 编译成功!")

        # 判断测试模式
        if Config.get("自动测试", 0) == 0 or len(Samples) == 0:
            # 手动测试模式
            print("🔄 开始手动样例测试")
            TestNum = 1
            while True:
                self.ManualTest(ResFile, TestNum, Config)
                TestNum += 1
                Order = input("\n是否继续测试? (y/n): ")
                if Order.lower() != 'y':
                    break
        else:
            # 自动测试模式
            print("🔄 开始自动样例测试\n")
            PassedCount = 0
            TotalSamples = len(Samples)
            for S in Samples:
                if self.AutoTest(ResFile, S, Config):
                    PassedCount += 1
            print(f"✅ 自动测试完成：{PassedCount}/{TotalSamples} 通过")
        try:
            os.remove(ResFile)
        except Exception as e:
            pass
        finally:
            print("已清理编译生成的文件")
        return

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 OITools.py Template [文件路径]    # 生成模板")
        print("  python3 OITools.py Test [文件路径]        # 运行测试")
        return

    Obj = OItools()
    Command = sys.argv[1]

    if Command == "Template":
        FilePath = sys.argv[2]
        Obj.ApplyTemplate(FilePath)
    elif Command == "Test":
        FilePath = sys.argv[2]
        Obj.Test(FilePath)
    else:
        print(f"❌ 未知命令: {Command}")

if __name__ == "__main__":
    main()