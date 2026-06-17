
import json
import os
import pandas as pd
import requests
import hashlib

from openai import OpenAI


class text_excel:
    def __init__(self, text_dir):
        self.text_dir = text_dir


    def __call__(self, text):

        client = OpenAI(
            api_key="",
            base_url="",
        )
        completion = client.chat.completions.create(
            model="moonshot-v1-128k",
            messages=[
                {
                    "role": "system",
                    "content": "你是一个在化学领域资深的教授，能帮我从文本中提取出需要的内容。"
                },
                {
                    "role": "user",
                    # Pristine perovskite(Control/Ctr)
                    # "content": f'请你专业性的角度告诉我这篇文章做的钙钛矿电池的制备信息，要包含具体含量比例等信息'+ text
                    "content": f'请你以专业性的角度告诉我这篇文章做的钙钛矿电池的制备信息，请保留具体的化学式（化学试剂用结构式或别名表示）、组成、比例以及含量等关键信息，请带着单位输出来' + text
                }
            ],
            temperature=0.3,
        )
        return completion.choices[0].message.content

    def __tran__(self):
        # 读取Excel文件
        for i in range(1, 20):
            file_path = os.path.join(self.text_dir, str(i)) + '.txt'
            file_path1 = os.path.join(self.text_dir, str(i)) + '-SI.txt'
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as file:
                    with open(file_path1, 'r', encoding='utf-8') as file1:
                        data = self.__call__('论文:' + file.read() + '。附录:' + file1.read())
                        data_final = data

                        print(data_final)

                        with open(fr'D:\钙钛矿\new\tk\output{i}.txt', 'a', encoding='utf-8') as file:
                            # 遍历列表中的每一行
                            file.write(data_final + '\n')




if __name__ == '__main__':
    text_dir = r'D:\钙钛矿\text_kimi'
    t = text_excel(text_dir)
    t.__tran__()



