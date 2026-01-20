#!/usr/bin/env python3
"""
批量测试脚本 - 多种子运行并计算平均值
自动读取实例文件夹，固定输出文件名
包含最优解GAP计算功能（简化版）
"""

import os
import sys
import subprocess
import re
import csv
import statistics
import argparse
from collections import defaultdict

def parse_solution_file(sol_file):
    """解析解文件，提取最优成本"""
    if not os.path.exists(sol_file):
        return None
    
    try:
        with open(sol_file, 'r') as f:
            lines = f.readlines()
            
            # 查找包含"Cost"的行
            for line in reversed(lines):  # 从后往前查找，通常Cost在最后
                if line.strip().startswith('Cost'):
                    # 匹配数字
                    match = re.search(r'Cost\s+(\d+(\.\d+)?)', line)
                    if match:
                        return float(match.group(1))
                
                # 或者匹配 "Cost 27591" 这种格式
                match = re.search(r'Cost\s+(\d+(\.\d+)?)', line)
                if match:
                    return float(match.group(1))
            
            # 如果没有找到Cost行，尝试其他格式
            for line in lines:
                # 匹配纯数字行（可能是单独的成本行）
                if re.match(r'^\d+(\.\d+)?$', line.strip()):
                    return float(line.strip())
                    
    except Exception as e:
        print(f"解析解文件 {sol_file} 时出错: {e}")
    
    return None

def parse_output(output):
    """解析命令输出，提取结果"""
    lines = output.strip().split('\n')
    results = {}
    
    # 查找结果行格式: X-n1001-k43   Y  75859.0        4801       5.0
    for i, line in enumerate(lines):
        if re.match(r'^\S+\s+[YN]\s+\d+\.?\d*\s+\d+\s+\d+\.?\d*$', line.strip()):
            parts = line.strip().split()
            if len(parts) >= 5:
                results['instance'] = parts[0]
                results['ok'] = parts[1]
                results['objective'] = float(parts[2])
                results['iterations'] = int(parts[3])
                results['time'] = float(parts[4])
                break
    
    # 查找汇总信息
    for line in lines:
        if 'Avg. objective:' in line:
            results['avg_objective'] = float(line.split(':')[1].strip())
        elif 'Avg. iterations:' in line:
            results['avg_iterations'] = float(line.split(':')[1].strip())
        elif 'Avg. run-time:' in line:
            results['avg_runtime'] = float(line.split(':')[1].strip().replace('s', ''))
        elif 'Total not OK:' in line:
            results['total_not_ok'] = int(line.split(':')[1].strip())
    
    return results

def run_single_test(instance, seed, max_runtime, best_cost=None):
    """运行单个测试实例"""
    cmd = [
        "uv", "run", "pyvrp",
        instance,
        "--seed", str(seed),
        "--max_runtime", str(max_runtime)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False
        )
        
        parsed = parse_output(result.stdout)
        
        if parsed:
            parsed['exit_code'] = result.returncode
            parsed['raw_output'] = result.stdout
            
            # 计算GAP（如果有最优成本）
            if best_cost is not None and best_cost > 0 and parsed['ok'] == 'Y':
                try:
                    gap = ((parsed['objective'] - best_cost) / best_cost) * 100
                    parsed['gap_percent'] = gap
                    parsed['best_cost'] = best_cost
                except (ZeroDivisionError, TypeError):
                    parsed['gap_percent'] = None
                    parsed['best_cost'] = best_cost
            else:
                parsed['gap_percent'] = None
                parsed['best_cost'] = best_cost
                
            return parsed
        else:
            result_dict = {
                'instance': os.path.basename(instance).replace('.vrp', ''),
                'ok': 'N',
                'objective': 0,
                'iterations': 0,
                'time': 0,
                'exit_code': result.returncode,
                'raw_output': result.stdout,
                'gap_percent': None,
                'best_cost': best_cost
            }
            return result_dict
            
    except Exception as e:
        print(f"执行出错: {e}")
        return None

def calculate_averages(results_list):
    """计算多个结果的平均值"""
    if not results_list:
        return {}
    
    # 提取所有有效的数值结果
    objectives = [r['objective'] for r in results_list if r and r['ok'] == 'Y']
    iterations = [r['iterations'] for r in results_list if r and r['ok'] == 'Y']
    times = [r['time'] for r in results_list if r and r['ok'] == 'Y']
    gaps = [r['gap_percent'] for r in results_list if r and r['ok'] == 'Y' and r['gap_percent'] is not None]
    
    ok_count = sum(1 for r in results_list if r and r['ok'] == 'Y')
    
    averages = {
        'instance': results_list[0]['instance'],
        'runs': len(results_list),
        'successful_runs': ok_count,
        'success_rate': ok_count / len(results_list) if results_list else 0,
        'best_cost': results_list[0].get('best_cost') if results_list and results_list[0] else None
    }
    
    # 计算平均值
    if objectives:
        averages['obj_avg'] = statistics.mean(objectives)
    else:
        averages['obj_avg'] = 0
    
    if iterations:
        averages['iters_avg'] = statistics.mean(iterations)
    else:
        averages['iters_avg'] = 0
    
    if times:
        averages['time_avg'] = statistics.mean(times)
    else:
        averages['time_avg'] = 0
    
    if gaps:
        averages['gap_avg'] = statistics.mean(gaps)
        averages['has_gap'] = True
    else:
        averages['gap_avg'] = None
        averages['has_gap'] = False
    
    return averages

def find_vrp_files(directories):
    """查找指定目录下的所有vrp文件，同时查找对应的解文件"""
    vrp_info_list = []  # 存储字典列表，每个字典包含实例文件路径和最优成本
    
    # 自然排序函数，用于按照数字顺序排序文件名
    def natural_sort_key(s):
        import re
        return [int(text) if text.isdigit() else text.lower() 
                for text in re.split(r'(\d+)', s)]
    
    for directory in directories:
        if os.path.exists(directory):
            print(f"扫描目录: {directory}")
            
            # 存储当前目录下的所有实例
            current_dir_instances = []
            
            # 查找所有.vrp文件
            for root, dirs, files in os.walk(directory):
                # 对目录进行自然排序
                dirs.sort(key=natural_sort_key)
                
                # 对文件进行自然排序
                vrp_files = [f for f in files if f.endswith('.vrp')]
                vrp_files.sort(key=natural_sort_key)
                
                for file in vrp_files:
                    instance_path = os.path.join(root, file)
                    instance_name = file.replace('.vrp', '')
                    
                    # 查找对应的.sol文件
                    sol_file_candidates = [
                        os.path.join(root, f"{instance_name}.sol"),
                        os.path.join(root, f"{instance_name}.sol.txt"),
                        os.path.join(root, f"{instance_name}.opt"),
                        os.path.join(root, f"{instance_name}.optimal")
                    ]
                    
                    best_cost = None
                    
                    # 尝试所有可能的解文件
                    for candidate in sol_file_candidates:
                        if os.path.exists(candidate):
                            best_cost = parse_solution_file(candidate)
                            if best_cost is not None:
                                print(f"  ✓ 找到解文件: {os.path.basename(candidate)}, 最优成本: {best_cost}")
                                break
                    
                    if best_cost is None:
                        print(f"  ! 未找到解文件: {instance_name}")
                    
                    # 添加到当前目录的实例列表
                    current_dir_instances.append({
                        'instance_path': instance_path,
                        'instance_name': instance_name,
                        'best_cost': best_cost,
                        'relative_path': os.path.relpath(instance_path, directory)
                    })
            
            # 将当前目录的实例按相对路径自然排序
            current_dir_instances.sort(key=lambda x: natural_sort_key(x['relative_path']))
            
            # 添加到总列表
            vrp_info_list.extend(current_dir_instances)
            
            print(f"在目录 {directory} 中找到 {len(current_dir_instances)} 个实例文件")
        else:
            print(f"警告: 目录不存在: {directory}")
    
    return vrp_info_list

def run_multi_seed_tests(vrp_info_list, seeds, max_runtime, detailed_csv="detailed_result.csv", summary_csv="summary_result.csv"):
    """运行多种子测试"""
    
    # 存储所有结果的字典
    all_averages = {}
    
    print(f"使用种子: {seeds}")
    print(f"最大运行时间: {max_runtime}秒")
    print(f"测试实例: {len(vrp_info_list)}个")
    print(f"详细结果CSV: {detailed_csv}")
    print(f"汇总结果CSV: {summary_csv}")
    
    # 统计解文件情况
    instances_with_sol = sum(1 for info in vrp_info_list if info['best_cost'] is not None)
    print(f"包含最优解文件的实例: {instances_with_sol}/{len(vrp_info_list)}")
    
    # 打开详细结果CSV文件
    with open(detailed_csv, 'w', newline='') as f_detail:
        detail_writer = csv.writer(f_detail)
        detail_writer.writerow(['Instance', 'Seed', 'Obj.', 'Best Obj.', 'GAP(%)', 'Iters', 'Time (s)', 'OK', 'Exit Code'])
        
        # 遍历所有实例
        for i, vrp_info in enumerate(vrp_info_list, 1):
            instance_path = vrp_info['instance_path']
            instance_name = vrp_info['instance_name']
            best_cost = vrp_info['best_cost']
            
            print(f"\n{'='*80}")
            print(f"[{i}/{len(vrp_info_list)}] 测试实例: {instance_name}")
            print(f"文件路径: {instance_path}")
            if best_cost is not None:
                print(f"最优成本: {best_cost}")
            else:
                print(f"最优成本: 未找到解文件")
            print('='*80)
            
            instance_results = []
            
            # 对每个种子运行测试
            for seed in seeds:
                print(f"\n--- 种子 {seed} ---")
                result = run_single_test(instance_path, seed, max_runtime, best_cost)
                
                if result:
                    # 准备写入CSV的数据
                    row_data = [
                        instance_name,
                        seed,
                        result['objective'],
                        best_cost if best_cost is not None else 'N/A',
                        f"{result['gap_percent']:.3f}" if result['gap_percent'] is not None else 'N/A',
                        result['iterations'],
                        result['time'],
                        result['ok'],
                        result['exit_code']
                    ]
                    
                    # 写入详细CSV
                    detail_writer.writerow(row_data)
                    
                    # 显示结果
                    status = "✓" if result['ok'] == 'Y' else "✗"
                    output_line = f"{status} 目标值: {result['objective']}"
                    
                    if best_cost is not None and result['gap_percent'] is not None:
                        output_line += f" (GAP: {result['gap_percent']:.2f}%)"
                    
                    output_line += f", 迭代: {result['iterations']}, 时间: {result['time']}s"
                    print(output_line)
                    
                    instance_results.append(result)
                else:
                    print(f"✗ 种子 {seed} 运行失败")
            
            # 计算平均值
            if instance_results:
                averages = calculate_averages(instance_results)
                all_averages[instance_name] = averages
                
                # 显示平均值信息
                print(f"\n--- {instance_name} 统计摘要 ---")
                print(f"成功运行: {averages['successful_runs']}/{averages['runs']} "
                      f"({averages['success_rate']:.1%})")
                
                if best_cost is not None:
                    print(f"最优成本: {best_cost}")
                
                print(f"目标值平均: {averages['obj_avg']:.2f}")
                
                if averages['has_gap']:
                    print(f"GAP平均: {averages['gap_avg']:.2f}%")
                
                print(f"迭代次数平均: {averages['iters_avg']:.0f}")
                print(f"运行时间平均: {averages['time_avg']:.2f}s")
            else:
                print(f"\n--- {instance_name} 统计摘要 ---")
                print("无成功运行")
    
    # 写入汇总CSV
    with open(summary_csv, 'w', newline='') as f_summary:
        summary_writer = csv.writer(f_summary)
        
        # 构建表头
        headers = [
            'Instance', 'Best Obj.', 'Runs', 'Successful', 'Success Rate',
            'Obj Avg', 'GAP Avg(%)', 'Iters Avg', 'Time Avg'
        ]
        
        summary_writer.writerow(headers)
        
        for instance_name, averages in all_averages.items():
            best_cost_str = f"{averages.get('best_cost', 'N/A'):.0f}" if averages.get('best_cost') is not None else 'N/A'
            
            if averages.get('has_gap', False) and averages['gap_avg'] is not None:
                gap_str = f"{averages['gap_avg']:.3f}"
            else:
                gap_str = 'N/A'
            
            summary_writer.writerow([
                instance_name,
                best_cost_str,
                averages['runs'],
                averages['successful_runs'],
                f"{averages['success_rate']:.3f}",
                f"{averages['obj_avg']:.2f}",
                gap_str,
                f"{averages['iters_avg']:.1f}",
                f"{averages['time_avg']:.2f}"
            ])
    
    print(f"\n{'='*80}")
    print("测试完成！")
    print(f"详细结果: {detailed_csv}")
    print(f"汇总结果: {summary_csv}")
    
    # 显示汇总表格
    if all_averages:
        print("\n汇总表格:")
        print("-" * 100)
        print(f"{'Instance':<20} {'Best':<10} {'Runs':<6} {'Success':<8} {'Obj Avg':<10} {'GAP Avg(%)':<12} {'Iters Avg':<10} {'Time Avg':<10}")
        print("-" * 100)
        
        for instance_name, averages in all_averages.items():
            best_cost_str = f"{averages.get('best_cost', 'N/A'):.0f}" if averages.get('best_cost') is not None else 'N/A'
            
            if averages.get('has_gap', False) and averages['gap_avg'] is not None:
                gap_str = f"{averages['gap_avg']:.2f}%"
            else:
                gap_str = 'N/A'
            
            print(f"{instance_name:<20} {best_cost_str:<10} "
                  f"{averages['runs']:<6} "
                  f"{averages['successful_runs']}/{averages['runs']:<7} "
                  f"{averages['obj_avg']:<10.2f} "
                  f"{gap_str:<12} "
                  f"{averages['iters_avg']:<10.0f} "
                  f"{averages['time_avg']:<10.2f}")
    else:
        print("无有效结果")

def main():
    parser = argparse.ArgumentParser(description='批量运行VRP测试（包含GAP计算）')
    parser.add_argument('--max_runtime', type=int, default=60, help='最大运行时间（秒）')
    parser.add_argument('--cvrp_dir', default='instance/CVRP', help='CVRP实例目录')
    parser.add_argument('--vrptw_dir', default='instance/VRPTW', help='VRPTW实例目录')
    parser.add_argument('--seeds', type=str, default='42,123,456,789,999', help='种子列表，用逗号分隔')
    parser.add_argument('--detailed_csv', default='detailed_result.csv', help='详细结果CSV文件名')
    parser.add_argument('--summary_csv', default='summary_result.csv', help='汇总结果CSV文件名')
    
    args = parser.parse_args()
    
    # 解析种子列表
    seeds = [int(seed.strip()) for seed in args.seeds.split(',')]
    
    # 查找实例文件
    instance_dirs = [args.cvrp_dir, args.vrptw_dir]
    vrp_info_list = find_vrp_files(instance_dirs)
    
    if not vrp_info_list:
        print("错误: 没有找到任何实例文件")
        sys.exit(1)
    
    # 显示找到的实例
    print("\n找到的实例文件:")
    for i, info in enumerate(vrp_info_list, 1):
        best_str = f"最优成本: {info['best_cost']}" if info['best_cost'] is not None else "无解文件"
        print(f"{i:3d}. {info['instance_name']:<30} ({best_str})")
    
    # 确认是否继续
    print(f"\n将测试 {len(vrp_info_list)} 个实例，使用 {len(seeds)} 个种子")
    response = input("是否继续? (y/n): ")
    if response.lower() != 'y':
        print("测试取消")
        sys.exit(0)
    
    # 运行多种子测试
    run_multi_seed_tests(
        vrp_info_list=vrp_info_list,
        seeds=seeds,
        max_runtime=args.max_runtime,
        detailed_csv=args.detailed_csv,
        summary_csv=args.summary_csv
    )

if __name__ == "__main__":
    main()#!/usr/bin/env python3
"""
批量测试脚本 - 多种子运行并计算平均值
自动读取实例文件夹，固定输出文件名
包含最优解GAP计算功能（简化版）
"""

import os
import sys
import subprocess
import re
import csv
import statistics
import argparse
from collections import defaultdict

def parse_solution_file(sol_file):
    """解析解文件，提取最优成本"""
    if not os.path.exists(sol_file):
        return None
    
    try:
        with open(sol_file, 'r') as f:
            lines = f.readlines()
            
            # 查找包含"Cost"的行
            for line in reversed(lines):  # 从后往前查找，通常Cost在最后
                if line.strip().startswith('Cost'):
                    # 匹配数字
                    match = re.search(r'Cost\s+(\d+(\.\d+)?)', line)
                    if match:
                        return float(match.group(1))
                
                # 或者匹配 "Cost 27591" 这种格式
                match = re.search(r'Cost\s+(\d+(\.\d+)?)', line)
                if match:
                    return float(match.group(1))
            
            # 如果没有找到Cost行，尝试其他格式
            for line in lines:
                # 匹配纯数字行（可能是单独的成本行）
                if re.match(r'^\d+(\.\d+)?$', line.strip()):
                    return float(line.strip())
                    
    except Exception as e:
        print(f"解析解文件 {sol_file} 时出错: {e}")
    
    return None

def parse_output(output):
    """解析命令输出，提取结果"""
    lines = output.strip().split('\n')
    results = {}
    
    # 查找结果行格式: X-n1001-k43   Y  75859.0        4801       5.0
    for i, line in enumerate(lines):
        if re.match(r'^\S+\s+[YN]\s+\d+\.?\d*\s+\d+\s+\d+\.?\d*$', line.strip()):
            parts = line.strip().split()
            if len(parts) >= 5:
                results['instance'] = parts[0]
                results['ok'] = parts[1]
                results['objective'] = float(parts[2])
                results['iterations'] = int(parts[3])
                results['time'] = float(parts[4])
                break
    
    # 查找汇总信息
    for line in lines:
        if 'Avg. objective:' in line:
            results['avg_objective'] = float(line.split(':')[1].strip())
        elif 'Avg. iterations:' in line:
            results['avg_iterations'] = float(line.split(':')[1].strip())
        elif 'Avg. run-time:' in line:
            results['avg_runtime'] = float(line.split(':')[1].strip().replace('s', ''))
        elif 'Total not OK:' in line:
            results['total_not_ok'] = int(line.split(':')[1].strip())
    
    return results

def run_single_test(instance, seed, max_runtime, best_cost=None):
    """运行单个测试实例"""
    cmd = [
        "uv", "run", "pyvrp",
        instance,
        "--seed", str(seed),
        "--max_runtime", str(max_runtime)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False
        )
        
        parsed = parse_output(result.stdout)
        
        if parsed:
            parsed['exit_code'] = result.returncode
            parsed['raw_output'] = result.stdout
            
            # 计算GAP（如果有最优成本）
            if best_cost is not None and best_cost > 0 and parsed['ok'] == 'Y':
                try:
                    gap = ((parsed['objective'] - best_cost) / best_cost) * 100
                    parsed['gap_percent'] = gap
                    parsed['best_cost'] = best_cost
                except (ZeroDivisionError, TypeError):
                    parsed['gap_percent'] = None
                    parsed['best_cost'] = best_cost
            else:
                parsed['gap_percent'] = None
                parsed['best_cost'] = best_cost
                
            return parsed
        else:
            result_dict = {
                'instance': os.path.basename(instance).replace('.vrp', ''),
                'ok': 'N',
                'objective': 0,
                'iterations': 0,
                'time': 0,
                'exit_code': result.returncode,
                'raw_output': result.stdout,
                'gap_percent': None,
                'best_cost': best_cost
            }
            return result_dict
            
    except Exception as e:
        print(f"执行出错: {e}")
        return None

def calculate_averages(results_list):
    """计算多个结果的平均值"""
    if not results_list:
        return {}
    
    # 提取所有有效的数值结果
    objectives = [r['objective'] for r in results_list if r and r['ok'] == 'Y']
    iterations = [r['iterations'] for r in results_list if r and r['ok'] == 'Y']
    times = [r['time'] for r in results_list if r and r['ok'] == 'Y']
    gaps = [r['gap_percent'] for r in results_list if r and r['ok'] == 'Y' and r['gap_percent'] is not None]
    
    ok_count = sum(1 for r in results_list if r and r['ok'] == 'Y')
    
    averages = {
        'instance': results_list[0]['instance'],
        'runs': len(results_list),
        'successful_runs': ok_count,
        'success_rate': ok_count / len(results_list) if results_list else 0,
        'best_cost': results_list[0].get('best_cost') if results_list and results_list[0] else None
    }
    
    # 计算平均值
    if objectives:
        averages['obj_avg'] = statistics.mean(objectives)
    else:
        averages['obj_avg'] = 0
    
    if iterations:
        averages['iters_avg'] = statistics.mean(iterations)
    else:
        averages['iters_avg'] = 0
    
    if times:
        averages['time_avg'] = statistics.mean(times)
    else:
        averages['time_avg'] = 0
    
    if gaps:
        averages['gap_avg'] = statistics.mean(gaps)
        averages['has_gap'] = True
    else:
        averages['gap_avg'] = None
        averages['has_gap'] = False
    
    return averages

def find_vrp_files(directories):
    """查找指定目录下的所有vrp文件，同时查找对应的解文件"""
    vrp_info_list = []  # 存储字典列表，每个字典包含实例文件路径和最优成本
    
    # 自然排序函数，用于按照数字顺序排序文件名
    def natural_sort_key(s):
        import re
        return [int(text) if text.isdigit() else text.lower() 
                for text in re.split(r'(\d+)', s)]
    
    for directory in directories:
        if os.path.exists(directory):
            print(f"扫描目录: {directory}")
            
            # 存储当前目录下的所有实例
            current_dir_instances = []
            
            # 查找所有.vrp文件
            for root, dirs, files in os.walk(directory):
                # 对目录进行自然排序
                dirs.sort(key=natural_sort_key)
                
                # 对文件进行自然排序
                vrp_files = [f for f in files if f.endswith('.vrp')]
                vrp_files.sort(key=natural_sort_key)
                
                for file in vrp_files:
                    instance_path = os.path.join(root, file)
                    instance_name = file.replace('.vrp', '')
                    
                    # 查找对应的.sol文件
                    sol_file_candidates = [
                        os.path.join(root, f"{instance_name}.sol"),
                        os.path.join(root, f"{instance_name}.sol.txt"),
                        os.path.join(root, f"{instance_name}.opt"),
                        os.path.join(root, f"{instance_name}.optimal")
                    ]
                    
                    best_cost = None
                    
                    # 尝试所有可能的解文件
                    for candidate in sol_file_candidates:
                        if os.path.exists(candidate):
                            best_cost = parse_solution_file(candidate)
                            if best_cost is not None:
                                print(f"  ✓ 找到解文件: {os.path.basename(candidate)}, 最优成本: {best_cost}")
                                break
                    
                    if best_cost is None:
                        print(f"  ! 未找到解文件: {instance_name}")
                    
                    # 添加到当前目录的实例列表
                    current_dir_instances.append({
                        'instance_path': instance_path,
                        'instance_name': instance_name,
                        'best_cost': best_cost,
                        'relative_path': os.path.relpath(instance_path, directory)
                    })
            
            # 将当前目录的实例按相对路径自然排序
            current_dir_instances.sort(key=lambda x: natural_sort_key(x['relative_path']))
            
            # 添加到总列表
            vrp_info_list.extend(current_dir_instances)
            
            print(f"在目录 {directory} 中找到 {len(current_dir_instances)} 个实例文件")
        else:
            print(f"警告: 目录不存在: {directory}")
    
    return vrp_info_list

def run_multi_seed_tests(vrp_info_list, seeds, max_runtime, detailed_csv="detailed_result.csv", summary_csv="summary_result.csv"):
    """运行多种子测试"""
    
    # 存储所有结果的字典
    all_averages = {}
    
    print(f"使用种子: {seeds}")
    print(f"最大运行时间: {max_runtime}秒")
    print(f"测试实例: {len(vrp_info_list)}个")
    print(f"详细结果CSV: {detailed_csv}")
    print(f"汇总结果CSV: {summary_csv}")
    
    # 统计解文件情况
    instances_with_sol = sum(1 for info in vrp_info_list if info['best_cost'] is not None)
    print(f"包含最优解文件的实例: {instances_with_sol}/{len(vrp_info_list)}")
    
    # 打开详细结果CSV文件
    with open(detailed_csv, 'w', newline='') as f_detail:
        detail_writer = csv.writer(f_detail)
        detail_writer.writerow(['Instance', 'Seed', 'Obj.', 'Best Obj.', 'GAP(%)', 'Iters', 'Time (s)', 'OK', 'Exit Code'])
        
        # 遍历所有实例
        for i, vrp_info in enumerate(vrp_info_list, 1):
            instance_path = vrp_info['instance_path']
            instance_name = vrp_info['instance_name']
            best_cost = vrp_info['best_cost']
            
            print(f"\n{'='*80}")
            print(f"[{i}/{len(vrp_info_list)}] 测试实例: {instance_name}")
            print(f"文件路径: {instance_path}")
            if best_cost is not None:
                print(f"最优成本: {best_cost}")
            else:
                print(f"最优成本: 未找到解文件")
            print('='*80)
            
            instance_results = []
            
            # 对每个种子运行测试
            for seed in seeds:
                print(f"\n--- 种子 {seed} ---")
                result = run_single_test(instance_path, seed, max_runtime, best_cost)
                
                if result:
                    # 准备写入CSV的数据
                    row_data = [
                        instance_name,
                        seed,
                        result['objective'],
                        best_cost if best_cost is not None else 'N/A',
                        f"{result['gap_percent']:.3f}" if result['gap_percent'] is not None else 'N/A',
                        result['iterations'],
                        result['time'],
                        result['ok'],
                        result['exit_code']
                    ]
                    
                    # 写入详细CSV
                    detail_writer.writerow(row_data)
                    
                    # 显示结果
                    status = "✓" if result['ok'] == 'Y' else "✗"
                    output_line = f"{status} 目标值: {result['objective']}"
                    
                    if best_cost is not None and result['gap_percent'] is not None:
                        output_line += f" (GAP: {result['gap_percent']:.2f}%)"
                    
                    output_line += f", 迭代: {result['iterations']}, 时间: {result['time']}s"
                    print(output_line)
                    
                    instance_results.append(result)
                else:
                    print(f"✗ 种子 {seed} 运行失败")
            
            # 计算平均值
            if instance_results:
                averages = calculate_averages(instance_results)
                all_averages[instance_name] = averages
                
                # 显示平均值信息
                print(f"\n--- {instance_name} 统计摘要 ---")
                print(f"成功运行: {averages['successful_runs']}/{averages['runs']} "
                      f"({averages['success_rate']:.1%})")
                
                if best_cost is not None:
                    print(f"最优成本: {best_cost}")
                
                print(f"目标值平均: {averages['obj_avg']:.2f}")
                
                if averages['has_gap']:
                    print(f"GAP平均: {averages['gap_avg']:.2f}%")
                
                print(f"迭代次数平均: {averages['iters_avg']:.0f}")
                print(f"运行时间平均: {averages['time_avg']:.2f}s")
            else:
                print(f"\n--- {instance_name} 统计摘要 ---")
                print("无成功运行")
    
    # 写入汇总CSV
    with open(summary_csv, 'w', newline='') as f_summary:
        summary_writer = csv.writer(f_summary)
        
        # 构建表头
        headers = [
            'Instance', 'Best Obj.', 'Runs', 'Successful', 'Success Rate',
            'Obj Avg', 'GAP Avg(%)', 'Iters Avg', 'Time Avg'
        ]
        
        summary_writer.writerow(headers)
        
        for instance_name, averages in all_averages.items():
            best_cost_str = f"{averages.get('best_cost', 'N/A'):.0f}" if averages.get('best_cost') is not None else 'N/A'
            
            if averages.get('has_gap', False) and averages['gap_avg'] is not None:
                gap_str = f"{averages['gap_avg']:.3f}"
            else:
                gap_str = 'N/A'
            
            summary_writer.writerow([
                instance_name,
                best_cost_str,
                averages['runs'],
                averages['successful_runs'],
                f"{averages['success_rate']:.3f}",
                f"{averages['obj_avg']:.2f}",
                gap_str,
                f"{averages['iters_avg']:.1f}",
                f"{averages['time_avg']:.2f}"
            ])
    
    print(f"\n{'='*80}")
    print("测试完成！")
    print(f"详细结果: {detailed_csv}")
    print(f"汇总结果: {summary_csv}")
    
    # 显示汇总表格
    if all_averages:
        print("\n汇总表格:")
        print("-" * 100)
        print(f"{'Instance':<20} {'Best':<10} {'Runs':<6} {'Success':<8} {'Obj Avg':<10} {'GAP Avg(%)':<12} {'Iters Avg':<10} {'Time Avg':<10}")
        print("-" * 100)
        
        for instance_name, averages in all_averages.items():
            best_cost_str = f"{averages.get('best_cost', 'N/A'):.0f}" if averages.get('best_cost') is not None else 'N/A'
            
            if averages.get('has_gap', False) and averages['gap_avg'] is not None:
                gap_str = f"{averages['gap_avg']:.2f}%"
            else:
                gap_str = 'N/A'
            
            print(f"{instance_name:<20} {best_cost_str:<10} "
                  f"{averages['runs']:<6} "
                  f"{averages['successful_runs']}/{averages['runs']:<7} "
                  f"{averages['obj_avg']:<10.2f} "
                  f"{gap_str:<12} "
                  f"{averages['iters_avg']:<10.0f} "
                  f"{averages['time_avg']:<10.2f}")
    else:
        print("无有效结果")

def main():
    parser = argparse.ArgumentParser(description='批量运行VRP测试（包含GAP计算）')
    parser.add_argument('--max_runtime', type=int, default=60, help='最大运行时间（秒）')
    parser.add_argument('--cvrp_dir', default='instance/CVRP', help='CVRP实例目录')
    parser.add_argument('--vrptw_dir', default='instance/VRPTW', help='VRPTW实例目录')
    parser.add_argument('--seeds', type=str, default='42,123,456,789,999', help='种子列表，用逗号分隔')
    parser.add_argument('--detailed_csv', default='detailed_result.csv', help='详细结果CSV文件名')
    parser.add_argument('--summary_csv', default='summary_result.csv', help='汇总结果CSV文件名')
    
    args = parser.parse_args()
    
    # 解析种子列表
    seeds = [int(seed.strip()) for seed in args.seeds.split(',')]
    
    # 查找实例文件
    instance_dirs = [args.cvrp_dir, args.vrptw_dir]
    vrp_info_list = find_vrp_files(instance_dirs)
    
    if not vrp_info_list:
        print("错误: 没有找到任何实例文件")
        sys.exit(1)
    
    # 显示找到的实例
    print("\n找到的实例文件:")
    for i, info in enumerate(vrp_info_list, 1):
        best_str = f"最优成本: {info['best_cost']}" if info['best_cost'] is not None else "无解文件"
        print(f"{i:3d}. {info['instance_name']:<30} ({best_str})")
    
    # 确认是否继续
    print(f"\n将测试 {len(vrp_info_list)} 个实例，使用 {len(seeds)} 个种子")
    response = input("是否继续? (y/n): ")
    if response.lower() != 'y':
        print("测试取消")
        sys.exit(0)
    
    # 运行多种子测试
    run_multi_seed_tests(
        vrp_info_list=vrp_info_list,
        seeds=seeds,
        max_runtime=args.max_runtime,
        detailed_csv=args.detailed_csv,
        summary_csv=args.summary_csv
    )

if __name__ == "__main__":
    main()