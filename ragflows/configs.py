#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# author：samge
# date：2024-08-23 16:49
# describe：

API_URL = 'http://192.168.66.36/v1'  # ragflow的api地址，请替换为实际的服务器地址
AUTHORIZATION = 'IjQ0ZjhmODVjNDVkNTExZjE5OWFiMDI0MmFjMTIwMDA2Ig.afVsew.mNGwWDuzQx8tUaz7RlAuZMepRUo'  # ragflow的api鉴权token
DIFY_DOC_KB_ID = '0acb52f4583811f1a48b0242ac120006'  # ragflow的知识库id
KB_NAME = "hj78"  # ragflow的知识库名称
PARSER_ID = "Paper"  # ragflow的知识库文档解析方式

DOC_DIR = '/public/ly/hj/documents/'    # 
DOC_SUFFIX = 'md,txt,pdf,docx'    # 指定文档后缀

MYSQL_HOST = 'localhost'
MYSQL_PORT = 5455
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'infini_rag_flow'
MYSQL_DATABASE = 'rag_flow'

# ========== Nanozyme Extraction Configuration ==========
CHAT_ID = "9faec032ebb811f0b4ce0242ac150006"
OPENAI_API_KEY = "ragflow-U4MThkYjI4ZDgzNDExZjA5NjJlMDI0Mm"
OPENAI_BASE_URL = "http://192.168.66.36:80/api/v1/chats_openai"

# 提取设置
EXTRACT_NANOZYME = True  # 是否提取纳米酶信息
EXTRACTION_WAIT_TIME = 3  # 提取间隔时间（秒）
STREAM_EXTRACTION = True  # 是否使用流式提取
INCLUDE_REFERENCES = False  # 不包含引用信息（只保存提取内容）

# 输出目录
NANOZYME_OUTPUT_DIR = "/public/ly/hj/ragflow-data-deepseek-r1:32b-xiaorong333"            

# 数据库操作
DELETE_FROM_DATABASE = True  # 从数据库中删除文档
KEEP_LOCAL_FILES = True  # 保留本地文档文件（不删除）


# 文档最少行数，低于该值的文档则被忽略，该参数仅作用于 txt,md,html 后缀文件
DOC_MIN_LINES = 1

# 是否仅上传文件。True=仅上传文件， False=上传文件+自动解析
ONLY_UPLOAD = False

# 是否打印切片进度查询日志。True=打印，False=不打印
ENABLE_PROGRESS_LOG = True

# 切片进度查询间隔时间（秒）
PROGRESS_CHECK_INTERVAL = 1

# 查数据库重试次数（单次重试间隔为1秒）
SQL_RETRIES = 0

# 首次上传后解析文件的等待时间
FIRST_PARSE_WAIT_TIME = 0

# 元数据后缀，需要跟上传文件放在同一目录，json格式。只有当该配置不为空时才会自动添加/更新元数据信息
METADATA_SUFFIX = ''    # 例如：.meta.json

def get_header():
    return {'authorization': AUTHORIZATION}