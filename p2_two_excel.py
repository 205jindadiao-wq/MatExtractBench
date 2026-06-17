
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
        deepseek_llm = OpenAI(base_url="",
                              api_key="")

        response = deepseek_llm.chat.completions.create(
            model="deepseek-v3-241226",
            messages=[
                {"role": "system", "content": "你是文本分析专家，能帮我从文本中提取出需要的内容。"},
                {"role": "user",
                 # "content": f'下面我会给你一个从钙钛矿电池的制备和实验论文中提取的关于钝化剂/修饰剂/添加剂的实验组和对照组信息，请你根据它们的作用方式区分一下'
                 #               'buried interface passivation agent(使用方式：'
                 #                    '溶液处理：在传输层表面涂覆钝化剂溶液，随后进行退火，形成钝化层。'
	             #                    '气相沉积：通过化学气相沉积（CVD）或原子层沉积（ALD）引入钝化剂。'
	             #                    '界面层设计：将钝化剂直接嵌入传输层中，或者与钙钛矿溶液共混。)'
                 #               'perovskite layer additives(使用方式：'
                 #                    '溶液法：将添加剂溶解在钙钛矿前驱液中，与前驱材料（如PbI₂、FAI等）混合。'
	             #                    '逐步涂覆法：在钙钛矿层制备过程中，添加剂可以分步加入，影响结晶或界面特性。'
	             #                    '蒸发或后处理：在钙钛矿层制备完成后，用添加剂溶液进行表面处理，提升表面和晶界特性。)'
                 #               'perovskite interface passivation agent(使用方式：'
                 #                    '溶液处理：通过溶液法将钝化剂涂覆在钙钛矿层表面，之后进行退火以促进钝化过程。'
	             #                    '气相沉积：利用原子层沉积（ALD）等气相沉积方法沉积钝化剂，精确控制钝化层的厚度和均匀性。'
	             #                    '蒸发或旋涂：通过蒸发或旋涂法将钝化剂沉积在钙钛矿表面，这些方法可高效地应用于大规模生产。)、'
                 #               '（没有的填入null，可能会出现组合使用）以上的信息请在content内以固定的json格式:'
                 #               '"buried interface passivation agent": ,'
                 #               '"perovskite layer additives": ,'
                 #               '"perovskite interface passivation agent": ,' + text

                 # #这是第一版的修改，问题：一些材料会被分为多个类别
                 # "content": f'下面我会给你一个从钙钛矿电池的制备和实验论文中提取的关于钝化剂/修饰剂/添加剂的实验组信息，请你根据它们的作用方式区分一下'
                 #          'buried interface passivation agent(使用方式：'
                 #            '溶液处理：在传输层表面涂覆钝化剂溶液，随后进行退火，形成钝化层。'
                 #            '气相沉积：通过化学气相沉积（CVD）或原子层沉积（ALD）引入钝化剂。'
                 #            '界面层设计：将钝化剂涂覆在电子传输层SnO2表面。)'
                 #          'perovskite layer additives(使用方式：'
                 #               '溶液法：将添加剂溶解在钙钛矿前驱液中，与前驱材料（如PbI₂、FAI等）)'
                 #          'perovskite interface passivation agent(使用方式：'
                 #            '溶液处理：通过溶液法将钝化剂涂覆在钙钛矿层表面，之后进行退火以促进钝化过程。'
                 #            '气相沉积：利用原子层沉积（ALD）等气相沉积方法沉积钝化剂，精确控制钝化层的厚度和均匀性。'
                 #            '蒸发或旋涂：通过蒸发或旋涂法将钝化剂沉积在钙钛矿表面，这些方法可高效地应用于大规模生产。)、'
                 #          '注意：没有的填入null，有些会有多组实验组用逗号区分开即可，每组只需给出化学表达式即可，不要多余的信息，以上的信息请在content内以固定的json格式:'
                 #          '"buried interface passivation agent": ,'
                 #          '"perovskite layer additives": ,'
                 #          '"perovskite interface passivation agent": ,' + text

                 "content": f'下面我会给你一个从钙钛矿电池的制备和实验论文中提取的关于钝化剂/修饰剂/添加剂的实验组和对照组信息，请你根据它们的作用方式区分一下'
                        '首先特别注意，一个实验组变量可能符合多个分类的标准，此时选择最符合的那一个，也就是一个实验变量只能分为一个类别'
                         'buried interface passivation agent(使用方式：'
                             '溶液处理：在钙钛矿层旋涂之前，在传输层（如SnO2电子传输层）表面涂覆钝化剂溶液，随后进行退火，形成钝化层；或者在SnO2溶液里面加入埋底钝化分子，随后进行退火，再旋涂钙钛矿层'
                             '气相沉积：通过化学气相沉积（CVD）或原子层沉积（ALD）引入钝化剂。'
                             '界面层设计：在钙钛矿层旋涂之前，将钝化剂涂覆在电子传输层SnO2表面。)'
                         'perovskite layer additives(使用方式：'
                            '溶液法：将添加剂溶解在钙钛矿前驱液中，与前驱材料（如PbI₂、FAI等）)，在涂覆完传输层后再旋涂钙钛矿前驱体溶液，退火形成钙钛矿层'
                         'perovskite interface passivation agent(使用方式：'
                             '溶液处理：涂覆完钙钛矿层并退火后，通过溶液法将钝化剂涂覆在钙钛矿层表面，之后进行退火以促进钝化过程。'
                             '气相沉积：利用原子层沉积（ALD）等气相沉积方法沉积钝化剂，精确控制钝化层的厚度和均匀性。'
                             '蒸发或旋涂：通过蒸发或旋涂法将钝化剂沉积在钙钛矿表面，这些方法可高效地应用于大规模生产。)、'
                         '注意：没有的填入null，有些会有多组实验组用逗号区分开即可，每组只需给出化学表达式即可，不要多余的信息，以上的信息请在content内以固定的json格式:'
                         '"buried interface passivation agent": ,'
                         '"perovskite layer additives": ,'
                         '"perovskite interface passivation agent": ,' + text

                 }
            ],
            stream=False,

        )
        print(f"返回的内容：{response.choices[0].message.content}")
        print(f"返回的类型：{type(response.choices[0].message.content)}")
        return response.choices[0].message.content

    def __tran__(self):
        # 读取Excel文件
        df = pd.read_excel(r'D:\钙钛矿\v1\标准数据格式.xlsx', sheet_name='Sheet1')  # 指定工作表名称，默认为第一个工作表
        pf = df[['Unnamed: 0']]
        #遍历返回的是一个元组（index,title）
        for item in pf[1:].itertuples(index=True, name=None):
            file_path = os.path.join(self.text_dir, 'output'+str(item[1])) + '.txt'
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as file:
                        data = self.__call__('' + file.read())
                        # data_final = json.loads(data)
                        data_final = data
                        first = data_final.find('{')
                        last = data_final.rfind('}')
                        data_final = data_final[first:last + 1]
                        try:
                            data_final = json.loads(data_final)  # 尝试JSON转换
                            print(data_final)  # 转换成功才执行输出

                            # 钝化剂从28开始
                            j = 28
                            df.loc[item[0], f'{df.columns[j]}'] = str(data_final['buried interface passivation agent'])
                            j = j + 1
                            df.loc[item[0], f'{df.columns[j]}'] = str(data_final['perovskite layer additives'])
                            j = j + 1
                            df.loc[item[0], f'{df.columns[j]}'] = str(
                                data_final['perovskite interface passivation agent'])
                            j = j + 1
                        except json.JSONDecodeError as e:
                            print(f"JSON转换失败: {e}")  # 捕获并显示转换错误
                        except Exception as e:
                            print(f"发生未知错误: {e}")  # 其他异常处理



            else:
                print(f"未找到：{item[1]}")
            print(f'{item[1]}询问处理完成')

        #将df写入一个新的excel文件？
        df.to_excel(r'C:\Users\wsh\Desktop\output\催化剂\o4.xlsx', index=False, header=False, sheet_name='Sheet1')


if __name__ == '__main__':
    text_dir = r'C:\Users\wsh\Desktop\output\催化剂\text'
    t = text_excel(text_dir)
    t.__tran__()



