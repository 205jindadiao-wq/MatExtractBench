#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import glob
import os
import time
import re
from openpyxl import load_workbook
from ragflows import api, configs
from utils import fileutils, timeutils
from pathlib import Path
from ragflows.param_extractor import NanozymeExtractor
from ragflows.db_utils_fixed import delete_document_from_db


def get_docs_files() -> list:
    """获取文档文件列表"""
    if not os.path.exists(configs.DOC_DIR):
        raise ValueError(f"文档目录configs.DOC_DIR（{configs.DOC_DIR}）不存在")
    
    all_files = []
    for ext in configs.DOC_SUFFIX.split(','):
        files = glob.glob(f'{configs.DOC_DIR}/**/*.{ext.strip()}', recursive=True)
        all_files.extend(files)
    return all_files


def load_nanozyme_xlsx(xlsx_file_path):
    """从XLSX首个工作表读取文档编号和Nanozyme Name。"""
    try:
        if not os.path.exists(xlsx_file_path):
            timeutils.print_log(f"错误: XLSX文件不存在: {xlsx_file_path}")
            return {}

        workbook = load_workbook(
            filename=xlsx_file_path,
            read_only=True,
            data_only=True,
        )
        try:
            worksheet = workbook.active
            nanozyme_dict = {}
            current_id = None

            for row in worksheet.iter_rows(values_only=True):
                values = list(row)
                if not any(
                    value is not None and str(value).strip()
                    for value in values
                ):
                    continue

                id_value = values[0] if values else None
                name_value = values[1] if len(values) > 1 else None
                id_text = '' if id_value is None else str(id_value).strip()
                name_text = '' if name_value is None else str(name_value).strip()

                normalized_id = re.sub(r'[\s_-]+', '', id_text).lower()
                normalized_name = re.sub(r'[\s_-]+', '', name_text).lower()
                if (
                    normalized_id in {'id', 'documentid', 'docid', '文档编号', '编号'}
                    or normalized_name in {
                        'nanozyme', 'nanozymename', '纳米酶', '纳米酶名称'
                    }
                ):
                    continue

                if id_text:
                    if isinstance(id_value, (int, float)) and not isinstance(id_value, bool):
                        if float(id_value).is_integer():
                            current_id = str(int(id_value))
                        else:
                            current_id = id_text
                    else:
                        number_groups = re.findall(r'(\d+)', id_text)
                        if number_groups:
                            current_id = str(int(number_groups[-1]))
                        else:
                            current_id = id_text

                if name_text and current_id:
                    nanozyme_dict.setdefault(current_id, []).append(name_text)
        finally:
            workbook.close()

        if nanozyme_dict:
            timeutils.print_log(
                f"成功从XLSX加载nanozyme数据，包含 {len(nanozyme_dict)} 个文档"
            )
        else:
            timeutils.print_log(
                "警告: XLSX中未加载到nanozyme数据，请确认A列为文档编号、"
                "B列为Nanozyme Name"
            )

        return nanozyme_dict

    except Exception as e:
        timeutils.print_log(f"加载XLSX文件时出错: {e}")
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
        # 使用文件名主体中最后一组数字，避免article_2020_366误映射到2020。
        number_groups = re.findall(r'(\d+)', Path(filename).stem)
        if number_groups:
            # 提取数字，转换为整数去除前导零，再转回字符串
            number_str = number_groups[-1]
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
    tuple: (提取成功, 删除成功, 文章中未找到目标材料, 模型字段提取不完整)
    """
    extraction_success = False
    deletion_success = False
    material_not_found = False
    model_extraction_failed = False
    
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
                validated_names = (
                    getattr(extractor, 'last_validated_names', None)
                    or nanozyme_names
                )
                saved_file = extractor.save_extraction_results(
                    content=content,
                    filename=filename,
                    doc_id=doc_id,
                    nanozyme_names=validated_names
                )
                
                if saved_file:
                    extraction_success = True
                    timeutils.print_log(f"提取完成，保存到: {saved_file}")
                else:
                    timeutils.print_log(f"保存文件失败")
            else:
                material_not_found = bool(
                    getattr(extractor, 'material_not_found', False)
                )
                model_extraction_failed = bool(
                    getattr(extractor, 'model_extraction_failed', False)
                )
                if material_not_found:
                    missing_names = (
                        getattr(extractor, 'last_unmatched_names', None)
                        or nanozyme_names
                    )
                    timeutils.print_log(
                        f"文章 {filename} 中没有材料: {', '.join(missing_names)}"
                    )
                elif model_extraction_failed:
                    timeutils.print_log(
                        f"模型未能完整提取 {filename} 的全部字段"
                    )
                else:
                    model_extraction_failed = True
                    timeutils.print_log(
                        f"提取内容为空，删除 {filename} 及其向量切片后继续下一篇"
                    )
                
        except Exception as e:
            timeutils.print_log(f"提取异常: {e}")
            import traceback
            timeutils.print_log(f"详细错误信息: {traceback.format_exc()}")
    elif getattr(configs, 'EXTRACT_NANOZYME', True):
        timeutils.print_log(f"跳过纳米酶提取: 未找到nanozyme名称")
        extraction_success = False
    else:
        timeutils.print_log(f"跳过纳米酶提取")
        extraction_success = False
    
    # 2. 提取成功、无目标材料、字段不完整或提取内容为空时，删除文档及其向量切片。
    if getattr(configs, 'DELETE_FROM_DATABASE', False):
        if extraction_success or material_not_found or model_extraction_failed:
            deletion_success = delete_document_from_db(filename, doc_id)
        else:
            timeutils.print_log(f"提取未成功，保留知识库文档: {filename}")
    else:
        timeutils.print_log(f"跳过数据库删除")
        deletion_success = False
    
    return (
        extraction_success,
        deletion_success,
        material_not_found,
        model_extraction_failed,
    )


def main():
    """主函数"""
    
    # 测试API连接
    status, msg = api.check_api_url()
    if not status:
        raise Exception(msg)
    
    # 加载nanozyme XLSX数据（A列：文档编号，B列：Nanozyme Name）
    xlsx_file_path = getattr(
        configs,
        'NANOZYME_XLSX_PATH',
        "/public/ly/hj/nanozyme_names1.xlsx",
    )
    nanozyme_dict = load_nanozyme_xlsx(xlsx_file_path)
    
    if not nanozyme_dict:
        raise RuntimeError(
            "XLSX未加载到任何nanozyme数据；为避免误删全部文档，批处理已停止"
        )
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
        exists, doc_info = api.check_document_exists(filename)
        
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
                    timeutils.print_log(f"尝试使用文档编号 {doc_number} 匹配XLSX数据")
                else:
                    # 如果无法提取文档编号，使用文档序号
                    doc_index = str(i+1)
                    nanozyme_names = nanozyme_dict.get(doc_index, [])
                    timeutils.print_log(f"无法提取文档编号，使用文档序号 {doc_index} 匹配XLSX数据")
                
                if nanozyme_names:
                    timeutils.print_log(f"找到 {len(nanozyme_names)} 个nanozyme名称用于提取")
                    # 直接处理，使用nanozyme名称列表
                    (
                        extraction_success,
                        deletion_success,
                        material_not_found,
                        model_extraction_failed,
                    ) = process_single_document_with_nanozymes(
                        filename, ragflow_doc_id, file_path, nanozyme_names
                    )
                else:
                    timeutils.print_log(
                        f"未找到文档编号 {doc_number} 对应的nanozyme名称，"
                        "跳过提取并准备删除该文档及向量切片"
                    )
                    extraction_success = False
                    material_not_found = True
                    model_extraction_failed = False
                    if getattr(configs, 'DELETE_FROM_DATABASE', False):
                        deletion_success = delete_document_from_db(
                            filename, ragflow_doc_id
                        )
                    else:
                        deletion_success = False
                
                if extraction_success:
                    extracted_count += 1
                if deletion_success:
                    deleted_count += 1
                if (
                    not extraction_success
                    and not material_not_found
                    and not model_extraction_failed
                ):
                    raise RuntimeError(
                        f"文档 {filename} 参数提取失败；文档已保留，"
                        "请查看上方具体提取错误。"
                    )
                if getattr(configs, 'DELETE_FROM_DATABASE', False) and not deletion_success:
                    raise RuntimeError(
                        f"文档 {filename} 未能完整删除文档记录和向量切片；"
                        "为避免污染下一篇，批处理已停止。"
                    )
                if material_not_found:
                    if deletion_success:
                        if nanozyme_names:
                            timeutils.print_log(
                                f"文章 {filename} 中没有目标材料，已删除文档及向量切片，继续下一篇"
                            )
                        else:
                            timeutils.print_log(
                                f"文档 {filename} 在XLSX中没有对应nanozyme名称，已删除文档及向量切片，继续下一篇"
                            )
                    else:
                        timeutils.print_log(
                            f"文档 {filename} 没有可提取的目标材料，未启用删除，继续下一篇"
                        )
                elif model_extraction_failed:
                    if deletion_success:
                        timeutils.print_log(
                            f"模型未能完整提取 {filename} 的字段，已删除文档及向量切片，继续下一篇"
                        )
                    else:
                        timeutils.print_log(
                            f"模型未能完整提取 {filename} 的字段，未启用删除，继续下一篇"
                        )
                    
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
                timeutils.print_log(f"尝试使用文档编号 {doc_number} 匹配XLSX数据")
            else:
                # 如果无法提取文档编号，使用文档序号
                doc_index = str(i+1)
                nanozyme_names = nanozyme_dict.get(doc_index, [])
                timeutils.print_log(f"无法提取文档编号，使用文档序号 {doc_index} 匹配XLSX数据")
            
            if nanozyme_names:
                timeutils.print_log(f"找到 {len(nanozyme_names)} 个nanozyme名称用于提取")
                # 处理文档，使用nanozyme名称列表
                (
                    extraction_success,
                    deletion_success,
                    material_not_found,
                    model_extraction_failed,
                ) = process_single_document_with_nanozymes(
                    filename, ragflow_doc_id, file_path, nanozyme_names
                )
            else:
                timeutils.print_log(
                    f"未找到文档编号 {doc_number} 对应的nanozyme名称，"
                    "跳过提取并准备删除该文档及向量切片"
                )
                extraction_success = False
                material_not_found = True
                model_extraction_failed = False
                if getattr(configs, 'DELETE_FROM_DATABASE', False):
                    deletion_success = delete_document_from_db(
                        filename, ragflow_doc_id
                    )
                else:
                    deletion_success = False
            
            if extraction_success:
                extracted_count += 1
            if deletion_success:
                deleted_count += 1
            if (
                not extraction_success
                and not material_not_found
                and not model_extraction_failed
            ):
                raise RuntimeError(
                    f"文档 {filename} 参数提取失败；文档已保留，"
                    "请查看上方具体提取错误。"
                )
            if getattr(configs, 'DELETE_FROM_DATABASE', False) and not deletion_success:
                raise RuntimeError(
                    f"文档 {filename} 未能完整删除文档记录和向量切片；"
                    "为避免污染下一篇，批处理已停止。"
                )
            if material_not_found:
                if deletion_success:
                    if nanozyme_names:
                        timeutils.print_log(
                            f"文章 {filename} 中没有目标材料，已删除文档及向量切片，继续下一篇"
                        )
                    else:
                        timeutils.print_log(
                            f"文档 {filename} 在XLSX中没有对应nanozyme名称，已删除文档及向量切片，继续下一篇"
                        )
                else:
                    timeutils.print_log(
                        f"文档 {filename} 没有可提取的目标材料，未启用删除，继续下一篇"
                    )
            elif model_extraction_failed:
                if deletion_success:
                    timeutils.print_log(
                        f"模型未能完整提取 {filename} 的字段，已删除文档及向量切片，继续下一篇"
                    )
                else:
                    timeutils.print_log(
                        f"模型未能完整提取 {filename} 的字段，未启用删除，继续下一篇"
                    )
        else:
            timeutils.print_log(f"解析失败")
            if getattr(configs, 'DELETE_FROM_DATABASE', False):
                raise RuntimeError(
                    f"文档 {filename} 解析失败且仍留在知识库中；"
                    "为避免污染下一篇，批处理已停止。"
                )
        
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
    
    # nanozyme XLSX数据统计
    total_nanozymes = sum(len(names) for names in nanozyme_dict.values())
    timeutils.print_log(f"XLSX中的nanozyme总数: {total_nanozymes}")
    timeutils.print_log(f"XLSX中的文档数: {len(nanozyme_dict)}")
    
    if processed_count > 0:
        completion_rate = (processed_count / file_total) * 100
        timeutils.print_log(f"完成比例: {processed_count}/{file_total} ({completion_rate:.1f}%)")
    
    timeutils.print_log('='*70)
    timeutils.print_log('处理完成！')


if __name__ == '__main__':
    main()
