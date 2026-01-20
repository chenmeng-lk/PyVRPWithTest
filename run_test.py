#!/usr/bin/env python3
"""
批量测试脚本 - 多种子运行并计算平均值
自动读取实例文件夹，固定输出文件名
"""

import os
import sys
import subprocess
import re
import csv
import statistics
import argparse
from collections import defaultdict

def parse_output(output):
    """解析命令输出，提取结果"""
    lines = output.strip().split('\n')
    results = {}
    
    # 查找结果行
    for i, line in enumerate(lines):
        # 匹配结果行格式: X-n1001-k43   Y  75859.0        4801       5.0
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

def run_single_test(instance, seed, max_runtime):
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
            return parsed
        else:
            return {
                'instance': os.path.basename(instance).replace('.vrp', ''),
                'ok': 'N',
                'objective': 0,
                'iterations': 0,
                'time': 0,
                'exit_code': result.returncode,
                'raw_output': result.stdout
            }
            
    except Exception as e:
        print(f"执行出错: {e}")
        return None

def calculate_statistics(results_list):
    """计算多个结果的统计信息"""
    if not results_list:
        return {}
    
    # 提取所有有效的数值结果
    objectives = [r['objective'] for r in results_list if r and r['ok'] == 'Y']
    iterations = [r['iterations'] for r in results_list if r and r['ok'] == 'Y']
    times = [r['time'] for r in results_list if r and r['ok'] == 'Y']
    ok_count = sum(1 for r in results_list if r and r['ok'] == 'Y')
    
    stats = {
        'instance': results_list[0]['instance'],
        'runs': len(results_list),
        'successful_runs': ok_count,
        'success_rate': ok_count / len(results_list) if results_list else 0
    }
    
    # 计算统计值
    if objectives:
        stats['obj_min'] = min(objectives)
        stats['obj_max'] = max(objectives)
        stats['obj_avg'] = statistics.mean(objectives)
        stats['obj_median'] = statistics.median(objectives)
        stats['obj_std'] = statistics.stdev(objectives) if len(objectives) > 1 else 0
    else:
        stats.update({'obj_min': 0, 'obj_max': 0, 'obj_avg': 0, 
                     'obj_median': 0, 'obj_std': 0})
    
    if iterations:
        stats['iters_min'] = min(iterations)
        stats['iters_max'] = max(iterations)
        stats['iters_avg'] = statistics.mean(iterations)
        stats['iters_median'] = statistics.median(iterations)
        stats['iters_std'] = statistics.stdev(iterations) if len(iterations) > 1 else 0
    else:
        stats.update({'iters_min': 0, 'iters_max': 0, 'iters_avg': 0, 
                     'iters_median': 0, 'iters_std': 0})
    
    if times:
        stats['time_min'] = min(times)
        stats['time_max'] = max(times)
        stats['time_avg'] = statistics.mean(times)
        stats['time_median'] = statistics.median(times)
        stats['time_std'] = statistics.stdev(times) if len(times) > 1 else 0
    else:
        stats.update({'time_min': 0, 'time_max': 0, 'time_avg': 0, 
                     'time_median': 0, 'time_std': 0})
    
    return stats

def find_vrp_files(directories):
    """查找指定目录下的所有vrp文件"""
    vrp_files = []
    
    for directory in directories:
        if os.path.exists(directory):
            # 查找所有.vrp文件
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.endswith('.vrp'):
                        full_path = os.path.join(root, file)
                        vrp_files.append(full_path)
            print(f"在目录 {directory} 中找到 {len([f for f in vrp_files if directory in f])} 个实例文件")
        else:
            print(f"警告: 目录不存在: {directory}")
    
    # 按文件名排序
    vrp_files.sort()
    return vrp_files

def run_multi_seed_tests(instances, seeds, max_runtime, detailed_csv="detailed_result.csv", summary_csv="summary_result.csv"):
    """运行多种子测试"""
    
    # 存储所有结果的字典
    all_results = defaultdict(list)
    
    print(f"使用种子: {seeds}")
    print(f"最大运行时间: {max_runtime}秒")
    print(f"测试实例: {len(instances)}个")
    print(f"详细结果CSV: {detailed_csv}")
    print(f"汇总结果CSV: {summary_csv}")
    
    # 打开详细结果CSV文件
    with open(detailed_csv, 'w', newline='') as f_detail:
        detail_writer = csv.writer(f_detail)
        detail_writer.writerow(['Instance', 'Seed', 'Obj.', 'Iters', 'Time (s)', 'OK', 'Exit Code'])
        
        # 遍历所有实例
        for i, instance in enumerate(instances, 1):
            instance_name = os.path.basename(instance).replace('.vrp', '')
            print(f"\n{'='*80}")
            print(f"[{i}/{len(instances)}] 测试实例: {instance_name}")
            print(f"文件路径: {instance}")
            print('='*80)
            
            instance_results = []
            
            # 对每个种子运行测试
            for seed in seeds:
                print(f"\n--- 种子 {seed} ---")
                result = run_single_test(instance, seed, max_runtime)
                
                if result:
                    # 写入详细CSV
                    detail_writer.writerow([
                        instance_name,
                        seed,
                        result['objective'],
                        result['iterations'],
                        result['time'],
                        result['ok'],
                        result['exit_code']
                    ])
                    
                    # 显示结果
                    status = "✓" if result['ok'] == 'Y' else "✗"
                    print(f"{status} 目标值: {result['objective']}, "
                          f"迭代: {result['iterations']}, "
                          f"时间: {result['time']}s, "
                          f"状态: {result['ok']}")
                    
                    instance_results.append(result)
                else:
                    print(f"✗ 种子 {seed} 运行失败")
            
            # 计算统计信息
            if instance_results:
                stats = calculate_statistics(instance_results)
                all_results[instance_name] = stats
                
                # 显示统计信息
                print(f"\n--- {instance_name} 统计摘要 ---")
                print(f"成功运行: {stats['successful_runs']}/{stats['runs']} "
                      f"({stats['success_rate']:.1%})")
                print(f"目标值: 平均={stats['obj_avg']:.2f}, "
                      f"范围=[{stats['obj_min']:.2f}, {stats['obj_max']:.2f}], "
                      f"标准差={stats['obj_std']:.2f}")
                print(f"迭代次数: 平均={stats['iters_avg']:.0f}, "
                      f"范围=[{stats['iters_min']}, {stats['iters_max']}], "
                      f"标准差={stats['iters_std']:.0f}")
                print(f"运行时间: 平均={stats['time_avg']:.2f}s, "
                      f"范围=[{stats['time_min']:.2f}, {stats['time_max']:.2f}]s, "
                      f"标准差={stats['time_std']:.2f}")
            else:
                print(f"\n--- {instance_name} 统计摘要 ---")
                print("无成功运行")
    
    # 写入汇总CSV
    with open(summary_csv, 'w', newline='') as f_summary:
        summary_writer = csv.writer(f_summary)
        summary_writer.writerow([
            'Instance', 'Runs', 'Successful', 'Success Rate',
            'Obj Min', 'Obj Max', 'Obj Avg', 'Obj Median', 'Obj Std',
            'Iters Min', 'Iters Max', 'Iters Avg', 'Iters Median', 'Iters Std',
            'Time Min', 'Time Max', 'Time Avg', 'Time Median', 'Time Std'
        ])
        
        for instance_name, stats in all_results.items():
            summary_writer.writerow([
                instance_name,
                stats['runs'],
                stats['successful_runs'],
                f"{stats['success_rate']:.3f}",
                f"{stats['obj_min']:.2f}",
                f"{stats['obj_max']:.2f}",
                f"{stats['obj_avg']:.2f}",
                f"{stats['obj_median']:.2f}",
                f"{stats['obj_std']:.2f}",
                int(stats['iters_min']),
                int(stats['iters_max']),
                f"{stats['iters_avg']:.1f}",
                f"{stats['iters_median']:.1f}",
                f"{stats['iters_std']:.1f}",
                f"{stats['time_min']:.2f}",
                f"{stats['time_max']:.2f}",
                f"{stats['time_avg']:.2f}",
                f"{stats['time_median']:.2f}",
                f"{stats['time_std']:.2f}"
            ])
    
    print(f"\n{'='*80}")
    print("测试完成！")
    print(f"详细结果: {detailed_csv}")
    print(f"汇总结果: {summary_csv}")
    
    # 显示汇总表格
    if all_results:
        print("\n汇总表格:")
        print("-" * 120)
        print(f"{'Instance':<20} {'Runs':<6} {'Success':<8} {'Obj Avg':<10} {'Iters Avg':<10} {'Time Avg':<10}")
        print("-" * 120)
        
        for instance_name, stats in all_results.items():
            print(f"{instance_name:<20} {stats['runs']:<6} "
                  f"{stats['successful_runs']}/{stats['runs']:<7} "
                  f"{stats['obj_avg']:<10.2f} "
                  f"{stats['iters_avg']:<10.0f} "
                  f"{stats['time_avg']:<10.2f}")
    else:
        print("无有效结果")

def main():
    parser = argparse.ArgumentParser(description='批量运行VRP测试')
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
    instances = find_vrp_files(instance_dirs)
    
    if not instances:
        print("错误: 没有找到任何实例文件")
        sys.exit(1)
    
    # 显示找到的实例
    print("\n找到的实例文件:")
    for i, instance in enumerate(instances, 1):
        print(f"{i:3d}. {instance}")
    
    # 确认是否继续
    print(f"\n将测试 {len(instances)} 个实例，使用 {len(seeds)} 个种子")
    response = input("是否继续? (y/n): ")
    if response.lower() != 'y':
        print("测试取消")
        sys.exit(0)
    
    # 运行多种子测试
    run_multi_seed_tests(
        instances=instances,
        seeds=seeds,
        max_runtime=args.max_runtime,
        detailed_csv=args.detailed_csv,
        summary_csv=args.summary_csv
    )

if __name__ == "__main__":
    main()