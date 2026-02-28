"""
性能统计工具
用于跟踪和报告导出流程中各个操作符的性能
"""
import time
from collections import defaultdict
from typing import Dict, List, Tuple


# 性能统计开关
PERFORMANCE_STATS_ENABLED = True


class PerformanceStats:
    """性能统计类"""
    
    def __init__(self):
        self.stats = defaultdict(lambda: {
            'total_time': 0.0,
            'count': 0,
            'start_time': None,
            'operation_times': []
        })
        self.operation_stack = []
        self.object_stats = defaultdict(lambda: {
            'total_time': 0.0,
            'operations': []
        })
    
    def start_operation(self, operation_name: str, obj_name: str = None):
        """开始一个操作"""
        if not PERFORMANCE_STATS_ENABLED:
            return
        
        now = time.time()
        self.operation_stack.append((operation_name, now, obj_name))
        self.stats[operation_name]['start_time'] = now
    
    def end_operation(self, operation_name: str = None):
        """结束一个操作"""
        if not PERFORMANCE_STATS_ENABLED:
            return
            
        if not self.operation_stack:
            return
        
        if operation_name is None:
            operation_name, start_time, obj_name = self.operation_stack.pop()
        else:
            # 查找匹配的操作
            for i, (op_name, start_time, obj_name) in enumerate(reversed(self.operation_stack)):
                if op_name == operation_name:
                    self.operation_stack.pop(-(i + 1))
                    break
            else:
                return
        
        end_time = time.time()
        duration = end_time - start_time
        
        # 更新统计
        self.stats[operation_name]['total_time'] += duration
        self.stats[operation_name]['count'] += 1
        self.stats[operation_name]['operation_times'].append(duration)
        self.stats[operation_name]['start_time'] = None
        
        # 记录物体级别的统计
        if obj_name:
            self.object_stats[obj_name]['total_time'] += duration
            self.object_stats[obj_name]['operations'].append({
                'operation': operation_name,
                'duration': duration
            })
    
    def get_operation_stats(self, operation_name: str) -> Dict:
        """获取指定操作的统计信息"""
        stats = self.stats[operation_name]
        if stats['count'] == 0:
            return {
                'operation': operation_name,
                'count': 0,
                'total_time': 0.0,
                'avg_time': 0.0,
                'min_time': 0.0,
                'max_time': 0.0,
                'objects_per_minute': 0.0
            }
        
        avg_time = stats['total_time'] / stats['count']
        min_time = min(stats['operation_times']) if stats['operation_times'] else 0.0
        max_time = max(stats['operation_times']) if stats['operation_times'] else 0.0
        
        # 计算每分钟可以处理的物体数量
        if avg_time > 0:
            objects_per_minute = 60.0 / avg_time
        else:
            objects_per_minute = 0.0
        
        return {
            'operation': operation_name,
            'count': stats['count'],
            'total_time': stats['total_time'],
            'avg_time': avg_time,
            'min_time': min_time,
            'max_time': max_time,
            'objects_per_minute': objects_per_minute
        }
    
    def get_all_stats(self) -> List[Dict]:
        """获取所有操作的统计信息"""
        all_stats = []
        for operation_name in sorted(self.stats.keys()):
            all_stats.append(self.get_operation_stats(operation_name))
        return all_stats
    
    def get_slowest_objects(self, limit: int = 10) -> List[Tuple[str, float, List]]:
        """获取处理最慢的物体"""
        sorted_objects = sorted(
            self.object_stats.items(),
            key=lambda x: x[1]['total_time'],
            reverse=True
        )
        return sorted_objects[:limit]
    
    def generate_report(self) -> str:
        """生成性能报告"""
        report = []
        report.append("=" * 80)
        report.append("导出流程性能统计报告")
        report.append("=" * 80)
        report.append("")
        
        # 总体统计
        total_time = sum(stats['total_time'] for stats in self.stats.values())
        total_operations = sum(stats['count'] for stats in self.stats.values())
        
        report.append(f"总处理时间: {total_time:.2f} 秒 ({total_time / 60:.2f} 分钟)")
        report.append(f"总操作次数: {total_operations}")
        report.append("")
        
        # 各操作统计
        report.append("-" * 80)
        report.append("各操作性能统计")
        report.append("-" * 80)
        report.append("")
        
        all_stats = self.get_all_stats()
        
        # 按总时间排序
        all_stats_sorted = sorted(all_stats, key=lambda x: x['total_time'], reverse=True)
        
        report.append(f"{'操作名称':<40} {'次数':>8} {'总时间(秒)':>12} {'平均时间(秒)':>14} {'每分钟处理数':>15}")
        report.append("-" * 80)
        
        for stat in all_stats_sorted:
            if stat['count'] > 0:
                report.append(
                    f"{stat['operation']:<40} "
                    f"{stat['count']:>8} "
                    f"{stat['total_time']:>12.2f} "
                    f"{stat['avg_time']:>14.4f} "
                    f"{stat['objects_per_minute']:>15.2f}"
                )
        
        report.append("")
        
        # 性能瓶颈分析
        report.append("-" * 80)
        report.append("性能瓶颈分析")
        report.append("-" * 80)
        report.append("")
        
        # 找出耗时最长的操作
        if all_stats_sorted:
            slowest_op = all_stats_sorted[0]
            if slowest_op['count'] > 0:
                time_percentage = (slowest_op['total_time'] / total_time * 100) if total_time > 0 else 0
                report.append(f"最耗时操作: {slowest_op['operation']}")
                report.append(f"  - 占总时间: {time_percentage:.2f}%")
                report.append(f"  - 执行次数: {slowest_op['count']}")
                report.append(f"  - 平均耗时: {slowest_op['avg_time']:.4f} 秒")
                report.append(f"  - 每分钟处理: {slowest_op['objects_per_minute']:.2f} 个物体")
                report.append("")
        
        # 找出处理速度最慢的操作
        slowest_speed_ops = [op for op in all_stats if op['objects_per_minute'] > 0 and op['objects_per_minute'] < 10]
        if slowest_speed_ops:
            slowest_speed_ops.sort(key=lambda x: x['objects_per_minute'])
            report.append("处理速度最慢的操作 (每分钟处理 < 10 个物体):")
            for op in slowest_speed_ops[:5]:
                report.append(f"  - {op['operation']}: {op['objects_per_minute']:.2f} 个/分钟")
            report.append("")
        
        # 处理最慢的物体
        report.append("-" * 80)
        report.append("处理最慢的物体 (Top 10)")
        report.append("-" * 80)
        report.append("")
        
        slowest_objects = self.get_slowest_objects(10)
        if slowest_objects:
            report.append(f"{'物体名称':<40} {'总时间(秒)':>12} {'操作次数':>10}")
            report.append("-" * 80)
            for obj_name, obj_stats in slowest_objects:
                report.append(
                    f"{obj_name:<40} "
                    f"{obj_stats['total_time']:>12.2f} "
                    f"{len(obj_stats['operations']):>10}"
                )
        else:
            report.append("无数据")
        
        report.append("")
        
        # 性能优化建议
        report.append("-" * 80)
        report.append("性能优化建议")
        report.append("-" * 80)
        report.append("")
        
        suggestions = self._generate_optimization_suggestions(all_stats_sorted)
        for suggestion in suggestions:
            report.append(f"• {suggestion}")
        
        report.append("")
        report.append("=" * 80)
        
        return "\n".join(report)
    
    def _generate_optimization_suggestions(self, all_stats: List[Dict]) -> List[str]:
        """生成性能优化建议"""
        suggestions = []
        
        # 检查是否有操作处理速度过慢
        slow_operations = [op for op in all_stats if op['objects_per_minute'] > 0 and op['objects_per_minute'] < 5]
        if slow_operations:
            suggestions.append(
                f"发现 {len(slow_operations)} 个操作处理速度过慢 (< 5个/分钟)，建议优化这些操作"
            )
        
        # 检查是否有操作时间波动过大
        for op in all_stats:
            if op['count'] > 10 and op['max_time'] > op['min_time'] * 10:
                suggestions.append(
                    f"操作 '{op['operation']}' 时间波动过大 (最小: {op['min_time']:.4f}s, 最大: {op['max_time']:.4f}s)，建议检查是否有异常物体"
                )
        
        # 检查并行处理是否启用
        parallel_stats = [op for op in all_stats if 'parallel' in op['operation'].lower()]
        if not parallel_stats:
            suggestions.append("未检测到并行处理，建议启用并行预处理以提升性能")
        
        return suggestions
    
    def print_report(self):
        """打印性能报告到控制台"""
        if not PERFORMANCE_STATS_ENABLED:
            return
            
        report = self.generate_report()
        print(report)
        return report
    
    def save_to_text_editor(self, text_name: str = "性能统计报告"):
        """将性能报告保存到Blender内置文本编辑器"""
        if not PERFORMANCE_STATS_ENABLED:
            return False
            
        try:
            import bpy
            
            report = self.generate_report()
            
            # 获取或创建文本块
            text_block = bpy.data.texts.get(text_name)
            if text_block:
                text_block.clear()
            else:
                text_block = bpy.data.texts.new(text_name)
            
            # 写入报告内容
            text_block.write(report)
            
            print(f"性能报告已保存到文本编辑器: {text_name}")
            return True
        except Exception as e:
            print(f"保存性能报告到文本编辑器失败: {e}")
            return False
    
    def reset(self):
        """重置统计"""
        self.stats.clear()
        self.operation_stack.clear()
        self.object_stats.clear()


# 全局性能统计实例
_global_performance_stats = PerformanceStats()


def get_performance_stats():
    """获取全局性能统计实例"""
    return _global_performance_stats


def start_operation(operation_name: str, obj_name: str = None):
    """开始一个操作"""
    _global_performance_stats.start_operation(operation_name, obj_name)


def end_operation(operation_name: str = None):
    """结束一个操作"""
    _global_performance_stats.end_operation(operation_name)


def print_performance_report():
    """打印性能报告"""
    return _global_performance_stats.print_report()


def save_performance_report_to_editor(text_name: str = "性能统计报告"):
    """保存性能报告到文本编辑器"""
    return _global_performance_stats.save_to_text_editor(text_name)


def reset_performance_stats():
    """重置性能统计"""
    _global_performance_stats.reset()


def set_performance_stats_enabled(enabled: bool):
    """设置性能统计开关"""
    global PERFORMANCE_STATS_ENABLED
    PERFORMANCE_STATS_ENABLED = enabled


def is_performance_stats_enabled() -> bool:
    """检查性能统计是否启用"""
    return PERFORMANCE_STATS_ENABLED
