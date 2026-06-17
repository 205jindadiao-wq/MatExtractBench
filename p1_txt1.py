
import json
import os
import pandas as pd
import requests
import hashlib

from openai import OpenAI


class text_excel:

    def __init__(self, text_dir, ):
        self.text_dir = text_dir

    #编码统一
    def __md5__(self, input_string):
        """
        对输入字符串进行MD5加密
        :param input_string: 需要加密的字符串
        :return: MD5加密后的十六进制字符串
        """
        # 创建md5对象
        md5_obj = hashlib.md5()
        # 将字符串编码为bytes后更新到md5对象中
        md5_obj.update(input_string.encode('utf-8'))
        # 获取十六进制格式的散列值
        return md5_obj.hexdigest()


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
                    "content": "你是文本分析专家，能帮我从文本中提取出需要的内容。"
                },
                {
                    # Pristine perovskite(Control/Ctr)
                    "role": "user",
                    # new:"content": '这是一篇关于钙钛矿电池的制备和实验论文，请你区分一下文中做多少组实验以及他们的钝化剂/修饰剂/添加剂分别是什么（可能会出现组合使用）以及他们分别作用于钙钛矿电池结构的哪一层上' + text
                    # v1版本
                    "content": '这是一篇关于钙钛矿电池的制备和实验论文，请你区分一下文中做多少组实验以及他们的钝化剂/修饰剂/添加剂分别是什么（可能会出现组合使用）、他们分别是如何被使用的、以及他们分别作用于钙钛矿电池结构的哪一层上' + text
                }
            ],
            temperature=0.3,
        )
        return completion.choices[0].message.content


    def __tran__(self):
        for i in range(1,20):
            file_path = os.path.join(self.text_dir, str(i)) + '.txt'
            file_path1 = os.path.join(self.text_dir, str(i)) + '-SI.txt'
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as file:
                    with open(file_path1, 'r', encoding='utf-8') as file1:
                        data = self.__call__('论文:' + file.read() + '。附录:' + file1.read())
                        print(data)
                        with open(fr'356.txt', 'a', encoding='utf-8') as file:
                            # 遍历列表中的每一行
                            file.write(data + '\n')




if __name__ == '__main__':
    text_dir = r'D:\钙钛矿\v1\text'
    t = text_excel(text_dir)
    t.__tran__()






