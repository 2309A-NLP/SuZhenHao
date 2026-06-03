# 导入命令行参数解析器，用于接收外部传入的运行参数
from argparse import ArgumentParser
# 导入HuggingFace Transformers库的自动分词器，用于加载预训练模型的分词工具
from transformers import AutoTokenizer
# 导入操作系统工具，用于文件路径创建、文件读写等操作
import os
# 导入随机数模块，用于负样本随机打乱、采样
import random
# 导入进度条工具，用于在命令行显示数据处理进度
from tqdm import tqdm
# 导入日期时间模块，用于生成随机数种子，保证随机性
from datetime import datetime
# 导入多进程池模块，用于加速数据处理，并行执行任务
from multiprocessing import Pool
# 导入自定义的训练数据处理器，专门用于处理MS MARO passage检索任务的训练数据
from dense.processor import MarcoPassageTrainProcessor as TrainProcessor

# 使用当前时间作为随机数种子，确保每次运行随机结果不同
random.seed(datetime.now())
# 初始化命令行参数解析器对象
parser = ArgumentParser()
# 添加必传参数：分词器模型名称/路径
parser.add_argument('--tokenizer_name', required=True)
# 添加必传参数：负样本文件路径（存储查询对应的负样本id）
parser.add_argument('--negative_file', required=True)
# 添加必传参数：相关性标注文件路径（查询与正样本文档的关联关系）
parser.add_argument('--qrels', required=True)
# 添加必传参数：查询语句文件路径（存储所有用户查询文本）
parser.add_argument('--queries', required=True)
# 添加必传参数：文档库文件路径（存储所有文档内容）
parser.add_argument('--collection', required=True)
# 添加必传参数：处理后的数据保存目录
parser.add_argument('--save_to', required=True)

# 添加可选参数：文本截断最大长度，默认128个token
parser.add_argument('--truncate', type=int, default=128)
# 添加可选参数：每个查询采样的负样本数量，默认30个
parser.add_argument('--n_sample', type=int, default=30)
# 添加可选参数：多进程处理时每批次处理的数据量，默认500条
parser.add_argument('--mp_chunk_size', type=int, default=500)
# 添加可选参数：每个数据分片的最大样本数，默认45000条
parser.add_argument('--shard_size', type=int, default=45000)

# 解析所有命令行传入的参数，赋值给args对象
args = parser.parse_args()


# 调用处理器的静态方法，读取查询-正样本相关性标注文件，返回字典格式
qrel = TrainProcessor.read_qrel(args.qrels)

# 定义单行数据处理函数：解析负样本文件的每一行数据
def read_line(l):
    # 去除行首尾空白字符，按制表符分割为 查询id 和 负样本id列表字符串
    q, nn = l.strip().split('\t')
    # 将负样本id字符串按逗号分割，转为列表
    nn = nn.split(',')
    # 随机打乱负样本列表顺序
    random.shuffle(nn)
    # 返回：查询id、该查询对应的正样本、采样后的前N个负样本
    return q, qrel[q], nn[:args.n_sample]


# 从指定名称/路径加载预训练分词器，使用快速分词器版本加速
tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_name, use_fast=True)
# 初始化训练数据处理器实例，配置查询文件、文档文件、分词器、最大文本长度
processor = TrainProcessor(
    query_file=args.queries,
    collection_file=args.collection,
    tokenizer=tokenizer,
    max_length=args.truncate,
)

# 初始化样本计数器，初始值为0
counter = 0
# 初始化数据分片编号，从0开始
shard_id = 0
# 初始化文件句柄，默认为空（未打开文件）
f = None
# 创建数据保存目录，已存在则不报错
os.makedirs(args.save_to, exist_ok=True)

# 打开负样本文件，只读模式
with open(args.negative_file) as nf:
    # 将负样本文件的每一行传入read_line函数，并用tqdm包裹显示处理进度
    pbar = tqdm(map(read_line, nf))

    # 创建多进程池，使用CPU核心数默认进程数
    with Pool() as p:
        # 多进程异步处理数据：每个进程处理一条数据，chunksize控制批次大小
        for x in p.imap(processor.process_one, pbar, chunksize=args.mp_chunk_size):
            # 每处理完一条样本，计数器+1
            counter += 1
            # 如果文件句柄为空（未打开文件），则创建新的分片文件
            if f is None:
                # 打开分片文件，命名格式：split00.json、split01.json...
                f = open(os.path.join(args.save_to, f'split{shard_id:02d}.json'), 'w')
                # 更新进度条描述，显示当前处理的分片编号
                pbar.set_description(f'split - {shard_id:02d}')
            # 将处理好的一行json数据写入文件，并换行
            f.write(x + '\n')

            # 判断：当前分片样本数达到设定最大值，需要切分新文件
            if counter == args.shard_size:
                # 关闭当前分片文件
                f.close()
                # 重置文件句柄为空
                f = None
                # 分片编号+1
                shard_id += 1
                # 重置样本计数器为0
                counter = 0

# 程序结束前，如果还有未关闭的文件，执行关闭操作
if f is not None:
    f.close()