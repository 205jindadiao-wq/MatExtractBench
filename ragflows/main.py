#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import glob
import os
import time
import csv
import pandas as pd
import re
from ragflows import api, configs, ragflowdb
from utils import fileutils, timeutils
from pathlib import Path
from ragflows.param_extractor import NanozymeExtractor
from ragflows.db_utils_fixed import delete_document_from_db, check_document_exists


def get_docs_files() -> list:
    """获取文档文件列表"""
    if not os.path.exists(configs.DOC_DIR):
        raise ValueError(f"文档目录configs.DOC_DIR（{configs.DOC_DIR}）不存在")
    
    all_files = []
    for ext in configs.DOC_SUFFIX.split(','):
        files = glob.glob(f'{configs.DOC_DIR}/**/*.{ext.strip()}', recursive=True)
        all_files.extend(files)
    return all_files


def load_nanozyme_csv(csv_file_path):
    """
    从CSV文件加载nanozyme数据 
    """
    try:
        if not os.path.exists(csv_file_path):
            timeutils.print_log(f"错误: CSV文件不存在!")
            return {}
        
        nanozyme_dict = {}
        
        # 尝试多种编码读取
        detected_encoding = None
        for encoding in ['gbk', 'gb2312', 'gb18030', 'latin1', 'iso-8859-1', 'cp1252', 'utf-8']:
            try:
                with open(csv_file_path, 'r', encoding=encoding) as f:
                    f.readline()
                detected_encoding = encoding
                break
            except:
                continue
        
        if not detected_encoding:
            detected_encoding = 'gbk'
        
        # 使用检测到的编码读取
        try:
            with open(csv_file_path, 'r', encoding=detected_encoding, errors='ignore') as f:
                content = f.read()
            
            lines = content.splitlines()
            current_id = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 跳过表头
                if line.lower().startswith('id') or line.lower().startswith('nanozyme'):
                    continue
                
                # 尝试按制表符分割
                if '\t' in line:
                    parts = line.split('\t', 1)
                # 尝试按逗号分割
                elif ',' in line and line.count(',') >= 1:
                    parts = line.split(',', 1)
                # 尝试按空格分割
                else:
                    match = re.match(r'^(\S+)\s+(\S.*)$', line)
                    if match:
                        parts = [match.group(1), match.group(2)]
                    else:
                        parts = [line]
                
                # 解析ID和nanozyme
                if len(parts) >= 2:
                    id_part = parts[0].strip()
                    name_part = parts[1].strip()
                    
                    # 处理ID部分
                    if id_part and id_part != '':
                        match = re.search(r'(\d+)', id_part)
                        if match:
                            current_id = str(int(match.group(1)))
                        else:
                            current_id = id_part
                    
                    # 处理nanozyme名称
                    if name_part and name_part != '' and current_id:
                        if current_id not in nanozyme_dict:
                            nanozyme_dict[current_id] = []
                        nanozyme_dict[current_id].append(name_part)
                
                elif len(parts) == 1 and current_id:
                    name_part = parts[0].strip()
                    if name_part and name_part != '':
                        if current_id not in nanozyme_dict:
                            nanozyme_dict[current_id] = []
                        nanozyme_dict[current_id].append(name_part)
        
        except Exception as read_error:
            timeutils.print_log(f"文件读取失败: {read_error}")
            return {}
        
        if nanozyme_dict:
            total_nanozymes = sum(len(names) for names in nanozyme_dict.values())
            timeutils.print_log(f"成功从CSV加载nanozyme数据，包含 {len(nanozyme_dict)} 个文档")
        else:
            timeutils.print_log("警告: 未加载到nanozyme数据")
        
        return nanozyme_dict
        
    except Exception as e:
        timeutils.print_log(f"加载CSV文件时出错: {e}")
        return {}


def extract_doc_number_from_filename(filename):
    """
    从文件名中提取文档编号
    
    Parameters:
    filename: 文件名，如 "001.pdf", "002.pdf", "411.pdf"等
    
    Returns:
    str: 文档编号字符串（去除前导零）
    """
    try:
        # 使用正则表达式提取数字部分
        match = re.search(r'(\d+)', filename)
        if match:
            # 提取数字，转换为整数去除前导零，再转回字符串
            number_str = match.group(1)
            return str(int(number_str))  # 这样"001"变成"1"，"002"变成"2"
        return None
    except Exception as e:
        timeutils.print_log(f"从文件名 {filename} 提取编号失败: {e}")
        return None


def need_calculate_lines(filepath) -> bool:
    if not filepath:
        return False
    suffix_lst = "txt,md,html".split(",")
    return filepath.split(".")[-1].lower() in suffix_lst


def get_file_lines(file_path) -> int:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return len(f.readlines())
    except Exception as e:
        timeutils.print_log(f"打开文件 {file_path} 时出错，错误信息：{e}")
        return 0


def process_single_document_with_nanozymes(filename, doc_id, file_path, nanozyme_names):
    """
    使用指定的nanozyme名称列表处理单个文档
    
    Parameters:
    filename: 文件名
    doc_id: RAGFlow文档ID
    file_path: 文件路径
    nanozyme_names: nanozyme名称列表
    
    Returns:
    tuple: (提取成功, 删除成功)
    """
    extraction_success = False
    deletion_success = False
    
    # 1. 提取纳米酶信息
    if getattr(configs, 'EXTRACT_NANOZYME', True) and nanozyme_names:
        timeutils.print_log(f"提取纳米酶信息: {filename} (找到 {len(nanozyme_names)} 个nanozyme)")
        
        try:
            # 创建NanozymeExtractor实例
            extractor = NanozymeExtractor(
                chat_id=getattr(configs, 'CHAT_ID', '9faec032ebb811f0b4ce0242ac150006')
            )
            
            # 提取参数
            timeutils.print_log(f"开始从文档 {doc_id} 提取 {len(nanozyme_names)} 个nanozyme的参数...")
            content = extractor.extract_nanozyme_parameters_from_list(
                filename=filename,
                doc_id=doc_id,
                nanozyme_names=nanozyme_names
            )
            
            if content:
                # 保存结果
                saved_file = extractor.save_extraction_results(
                    content=content,
                    filename=filename,
                    doc_id=doc_id,
                    nanozyme_names=nanozyme_names
                )
                
                if saved_file:
                    extraction_success = True
                    timeutils.print_log(f"提取完成，保存到: {saved_file}")
                else:
                    timeutils.print_log(f"保存文件失败")
            else:
                timeutils.print_log(f"提取内容为空")
                
        except Exception as e:
            timeutils.print_log(f"提取异常: {e}")
            import traceback
            timeutils.print_log(f"详细错误信息: {traceback.format_exc()}")
    elif getattr(configs, 'EXTRACT_NANOZYME', True):
        timeutils.print_log(f"跳过纳米酶提取: 未找到nanozyme名称")
        extraction_success = True
    else:
        timeutils.print_log(f"跳过纳米酶提取")
        extraction_success = True
    
    # 2. 从数据库中删除文档
    if getattr(configs, 'DELETE_FROM_DATABASE', True):
        deletion_success = delete_document_from_db(filename, doc_id)
    else:
        timeutils.print_log(f"跳过数据库删除")
        deletion_success = True
    
    return extraction_success, deletion_success


def main():
    """主函数"""
    
    # 测试数据库连接
    db = ragflowdb.get_db()
    if not db or not db.conn:
        raise Exception("无法连接到数据库，请检查数据库配置是否正确")
    
    # 测试API连接
    status, msg = api.check_api_url()
    if not status:
        raise Exception(msg)
    
    # 加载nanozyme CSV数据
    csv_file_path = getattr(configs, 'NANOZYME_CSV_PATH', "/public/ly/hj/nanozyme_names.csv")
    nanozyme_dict = load_nanozyme_csv(csv_file_path)
    
    if not nanozyme_dict:
        timeutils.print_log("警告: 未加载到nanozyme数据，将跳过nanozyme提取")
    else:
        timeutils.print_log(f"已加载nanozyme数据，覆盖 {len(nanozyme_dict)} 个文档")
    
    # 获取起始文件序号
    user_config_dir = os.path.join(Path.home(), '.ragflow_upload')
    os.makedirs(user_config_dir, exist_ok=True)
    index_filepath = f"{user_config_dir}/index_{configs.DIFY_DOC_KB_ID}_{configs.KB_NAME}.txt".replace(os.sep, "/")
    start_index = int(fileutils.read(index_filepath) or 1)
    if start_index < 1:
        raise ValueError(f"【起始文件序号】值不能小于1，请改为大于等于1的值，或者删除序号缓存文件：{index_filepath}")
    
    # 获取所有文档文件
    doc_files = get_docs_files() or []
    
    file_total = len(doc_files)
    if file_total == 0:
        raise ValueError(f"在 {configs.DOC_DIR} 目录下没有找到符合要求文档文件") 
    
    if start_index > file_total:
        raise ValueError(f"起始文件序号 {start_index} > 文件总数 {file_total}，请修改为正确的序号值，或者删除序号缓存文件：{index_filepath}")
    
    # 打印信息
    timeutils.print_log(f"找到 {file_total} 个本地文档文件")
    timeutils.print_log(f"起始序号: {start_index}")
    timeutils.print_log(f"纳米酶提取: {'启用' if getattr(configs, 'EXTRACT_NANOZYME', True) else '❌ 禁用'}")
    timeutils.print_log(f"从数据库删除: {'启用' if getattr(configs, 'DELETE_FROM_DATABASE', True) else '❌ 禁用'}")
    
    # 处理文件
    processed_count = 0
    extracted_count = 0
    deleted_count = 0
    
    for i in range(file_total):
        
        if i < start_index - 1:
            continue
        
        file_path = doc_files[i]
        
        # 跳过元数据文件
        if configs.METADATA_SUFFIX and file_path.endswith(configs.METADATA_SUFFIX):
            continue
        
        file_path = file_path.replace(os.sep, '/')
        filename = os.path.basename(file_path)
        
        timeutils.print_log(f"\n{'='*70}")
        timeutils.print_log(f"【{i+1}/{file_total}】处理: {filename}")
        timeutils.print_log(f"{'='*70}")
        
        # 记录文件序号
        fileutils.save(index_filepath, str(i+1))
        
        # 检查文件行数
        if need_calculate_lines(file_path):
            file_lines = get_file_lines(file_path)
            if file_lines < configs.DOC_MIN_LINES:
                timeutils.print_log(f"行数低于{configs.DOC_MIN_LINES}，跳过")
                continue
        
        processed_count += 1
        
        # 从文件名中提取文档编号
        doc_number = extract_doc_number_from_filename(filename)
        timeutils.print_log(f"从文件名提取的文档编号: {doc_number}")
        
        # 检查文档是否已在数据库中
        exists, doc_info = check_document_exists(filename)
        
        if exists and doc_info:
            ragflow_doc_id = doc_info['id']  # RAGFlow数据库中的文档ID
            progress = doc_info['progress']
            
            if progress == 1:
                timeutils.print_log(f"文档已在数据库中并已解析完成")
                timeutils.print_log(f"RAGFlow文档ID: {ragflow_doc_id}")
                
                # 获取当前文档对应的nanozyme名称
                # 使用从文件名提取的编号，而不是文档序号
                if doc_number:
                    nanozyme_names = nanozyme_dict.get(doc_number, [])
                    timeutils.print_log(f"尝试使用文档编号 {doc_number} 匹配CSV数据")
                else:
                    # 如果无法提取文档编号，使用文档序号
                    doc_index = str(i+1)
                    nanozyme_names = nanozyme_dict.get(doc_index, [])
                    timeutils.print_log(f"无法提取文档编号，使用文档序号 {doc_index} 匹配CSV数据")
                
                if nanozyme_names:
                    timeutils.print_log(f"找到 {len(nanozyme_names)} 个nanozyme名称用于提取")
                    # 直接处理，使用nanozyme名称列表
                    extraction_success, deletion_success = process_single_document_with_nanozymes(
                        filename, ragflow_doc_id, file_path, nanozyme_names
                    )
                else:
                    timeutils.print_log(f"未找到文档编号 {doc_number} 对应的nanozyme名称，跳过提取")
                    # 只进行删除操作
                    if getattr(configs, 'DELETE_FROM_DATABASE', True):
                        deletion_success = delete_document_from_db(filename, ragflow_doc_id)
                    else:
                        deletion_success = True
                    extraction_success = False
                
                if extraction_success:
                    extracted_count += 1
                if deletion_success:
                    deleted_count += 1
                    
                continue
            else:
                timeutils.print_log(f"文档在数据库中但未解析完成 (进度: {progress})")
                # 需要重新解析
        
        # 上传文档
        timeutils.print_log(f"⬆️  上传文件: {filename}")
        response = api.upload_file_to_kb(
            file_path=file_path, 
            kb_name=configs.KB_NAME, 
            kb_id=configs.DIFY_DOC_KB_ID,
            parser_id=configs.PARSER_ID, 
            run="1"
        )
        
        if api.is_succeed(response) is False:
            timeutils.print_log(f'上传失败')
            continue
        
        timeutils.print_log(f"上传成功")
        
        # 获取RAGFlow文档ID
        data = response.get('data')
        ragflow_doc_id = None
        if isinstance(data, list) and data and isinstance(data[0], dict):
            ragflow_doc_id = data[0].get('id')
        elif isinstance(data, dict):
            ragflow_doc_id = data.get('id')
        
        # 更新元数据
        if ragflow_doc_id:
            api.set_document_metadata(ragflow_doc_id, file_path)
        
        # 仅上传，跳过切片解析
        if configs.ONLY_UPLOAD:
            continue
        
        # 首次上传等待
        if i == start_index - 1 and configs.FIRST_PARSE_WAIT_TIME > 0:
            timeutils.print_log(f'首次上传，等待 {configs.FIRST_PARSE_WAIT_TIME} 秒...')
            time.sleep(configs.FIRST_PARSE_WAIT_TIME)
        
        # 切片解析
        timeutils.print_log(f'开始切片解析')
        status = api.parse_chunks_with_check(filename, ragflow_doc_id)
        
        if status:
            timeutils.print_log(f"解析完成")
            timeutils.print_log(f"RAGFlow文档ID: {ragflow_doc_id}")
            
            # 获取当前文档对应的nanozyme名称
            # 使用从文件名提取的编号
            if doc_number:
                nanozyme_names = nanozyme_dict.get(doc_number, [])
                timeutils.print_log(f"尝试使用文档编号 {doc_number} 匹配CSV数据")
            else:
                # 如果无法提取文档编号，使用文档序号
                doc_index = str(i+1)
                nanozyme_names = nanozyme_dict.get(doc_index, [])
                timeutils.print_log(f"无法提取文档编号，使用文档序号 {doc_index} 匹配CSV数据")
            
            if nanozyme_names:
                timeutils.print_log(f"找到 {len(nanozyme_names)} 个nanozyme名称用于提取")
                # 处理文档，使用nanozyme名称列表
                extraction_success, deletion_success = process_single_document_with_nanozymes(
                    filename, ragflow_doc_id, file_path, nanozyme_names
                )
            else:
                timeutils.print_log(f"未找到文档编号 {doc_number} 对应的nanozyme名称，跳过提取")
                # 只进行删除操作
                if getattr(configs, 'DELETE_FROM_DATABASE', True):
                    deletion_success = delete_document_from_db(filename, ragflow_doc_id)
                else:
                    deletion_success = True
                extraction_success = False
            
            if extraction_success:
                extracted_count += 1
            if deletion_success:
                deleted_count += 1
        else:
            timeutils.print_log(f"解析失败")
        
        # 等待
        wait_time = getattr(configs, 'EXTRACTION_WAIT_TIME', 3)
        if wait_time > 0 and (i + 1) < file_total:
            timeutils.print_log(f"等待 {wait_time} 秒...")
            time.sleep(wait_time)
    
    # 统计
    timeutils.print_log('\n' + '='*70)
    timeutils.print_log('处理完成统计')
    timeutils.print_log('='*70)
    timeutils.print_log(f"本地文件总数: {file_total}")
    timeutils.print_log(f"已处理文件: {processed_count}")
    timeutils.print_log(f"纳米酶提取成功: {extracted_count}")
    timeutils.print_log(f"从数据库删除: {deleted_count}")
    
    # nanozyme数据统计
    total_nanozymes = sum(len(names) for names in nanozyme_dict.values())
    timeutils.print_log(f"CSV中的nanozyme总数: {total_nanozymes}")
    timeutils.print_log(f"CSV中的文档数: {len(nanozyme_dict)}")
    
    if processed_count > 0:
        completion_rate = (processed_count / file_total) * 100
        timeutils.print_log(f"完成比例: {processed_count}/{file_total} ({completion_rate:.1f}%)")
    
    timeutils.print_log('='*70)
    timeutils.print_log('处理完成！')


if __name__ == '__main__':
    main()