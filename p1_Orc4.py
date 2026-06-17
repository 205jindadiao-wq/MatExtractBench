import os
from multiprocessing import Process
from time import sleep
import pandas as pd
import json
from openpyxl import load_workbook
import base64
import requests
from gradio_client import Client, handle_file
from requests_toolbelt import MultipartEncoder
import os


class pdf_text:

    def __init__(self, pdf_dir, text_dir):
        self.pdf_dir = pdf_dir
        self.text_dir = text_dir


    def image_text(self, path):

        # 文件上传上下文管理
        with open(path, 'rb') as file:
            # API调用核心逻辑
            response = requests.post(
                '',
                params={
                    'parse_method': 'auto',
                    'is_json_md_dump': 'false',
                    'return_layout': 'false',
                    'return_info': 'false',
                    'return_content_list': 'true',
                    'return_images': 'true',
                    'return_word': 'true',
                    'return_entity_image': 'false'
                },
                files={'pdf_file': (path.split('/')[-1], file)},
                headers={'User-Agent': 'Apifox/1.0.0'},
                timeout=600
            )
            response.raise_for_status()

        # 响应解析适配层
        result = response.json()
        text_content = result['md_content']
        return  text_content


    def __tran__(self):
        for filename in os.listdir(pdf_dir):
            # 构建文件的完整路径
            file_path = os.path.join(pdf_dir, filename)

            # 检查是否为文件（排除子文件夹）
            if os.path.isfile(file_path):
                # 提取文件名（不包含扩展名）
                base_name = os.path.splitext(filename)[0]

                # 构建新的文件名（.txt扩展名）
                new_filename = f"{base_name}.txt"

                # 构建新文件的完整路径
                new_file_path = os.path.join(text_dir, new_filename)

                text = self.image_text(file_path)
                # 写入内容到新文件
                with open(new_file_path, 'w', encoding='utf-8') as file:
                    file.write(text)

                print(f"文件 '{filename}' 已转换为 '{new_filename}' 并保存。")


if __name__ == '__main__':
    # pdf_dir = r'D:\钙钛矿\1-10\pdf'
    # text_dir = r'D:\钙钛矿\1-10\text'
    pdf_dir = r'tiqupdf'
    text_dir = r'tiqutxt'


    text = pdf_text(pdf_dir, text_dir)
    text.__tran__()


