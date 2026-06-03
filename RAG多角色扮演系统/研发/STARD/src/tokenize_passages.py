# 导入命令行参数解析器，用于接收外部运行时传入的参数
from argparse import ArgumentParser
# 导入Hugging Face Transformers库中的自动分词器，用于加载预训练模型的分词工具
from transformers import AutoTokenizer
# 导入操作系统模块，用于文件路径处理、文件夹创建等操作
import os
# 导入进度条工具，用于在控制台显示数据处理进度
from tqdm import tqdm
# 导入多进程池，用于开启多进程加速数据处理速度
from multiprocessing import Pool
# 导入自定义的文档处理类，用于对文本数据进行编码、格式化等预处理操作
from dense.processor import SimpleCollectionProcessor

# 创建命令行参数解析器对象
parser = ArgumentParser()
# 添加必传参数：分词器模型名称或本地路径
parser.add_argument('--tokenizer_name', required=True)
# 添加可选参数：文本最大截断长度，默认128个token
parser.add_argument('--truncate', type=int, default=128)
# 添加必传参数：需要处理的原始文本文件路径
parser.add_argument('--file', required=True)
# 添加必传参数：处理完成后的数据保存路径
parser.add_argument('--save_to', required=True)
# 添加可选参数：将数据切分为多少个文件分片，默认10个分片
parser.add_argument('--n_splits', type=int, default=10)

# 解析命令行传入的所有参数，赋值给args对象
args = parser.parse_args()

# 根据指定的模型名称/路径加载预训练分词器，使用快速分词器提升处理速度
tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_name, use_fast=True)
# 初始化文档处理器，传入分词器和文本最大长度
processor = SimpleCollectionProcessor(tokenizer=tokenizer, max_length=args.truncate)

# 以只读模式打开原始文本文件
with open(args.file, 'r') as f:
    # 一次性读取文件所有行，存储到lines列表中
    lines = f.readlines()

# 获取文本文件的总行数
n_lines = len(lines)
# 判断总行数是否能被分片数整除
if n_lines % args.n_splits == 0:
    # 能整除，计算每个分片的行数
    split_size = int(n_lines / args.n_splits)
else:
    # 不能整除，每个分片行数+1，保证所有数据都能被分配
    split_size = int(n_lines / args.n_splits) + 1

# 创建数据保存目录，如果目录已存在则不报错
os.makedirs(args.save_to, exist_ok=True)
# 创建多进程池，使用系统默认的进程数（CPU核心数）
with Pool() as p:
    # 循环遍历所有分片，逐个处理
    for i in range(args.n_splits):
        # 打开当前分片的输出文件，写入模式
        with open(os.path.join(args.save_to, f'split{i:02d}.json'), 'w') as f:
            # 截取当前分片对应的文本行，并创建进度条
            pbar = tqdm(lines[i*split_size: (i+1)*split_size])
            # 设置进度条描述，显示当前处理的分片编号
            pbar.set_description(f'split - {i:02d}')
            # 多进程并行处理每一行文本，chunksize=500表示每批次分配500行数据
            for jitem in p.imap(processor.process_line, pbar, chunksize=500):
                # 将处理后的结果写入文件，每行末尾添加换行符
                f.write(jitem + '\n')