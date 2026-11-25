import argparse
import os
import csv
from pathlib import Path



import ollama

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        print("请先安装pymupdf包: pip install pymupdf")
        exit(1)

MODEL_LIST = [

    #"qwen2.5:7b",
    #"deepseek-r1:14b",
    #"qwen2.5:14b",
    "deepseek-v2:16b",
    #"deepseek-r1:32b",
    #"qwen2:7b",
    #"llama3:8b",
    
    #"llama3.1:8b",
    #"deepseek-r1:1.5b",
    #"deepseek-r1:7b",
    #"mistral:7b",
    #"gemma2:9b",
    #"granite3.3:8b",

    #"openthinker:7b",
    #"mistral-nemo:12b",
    #"llava-llama3:8b",
    #"gemma:7b",
    #"glm4:9b",
    #"dolphin3:8b",


    # "openthinker:32b",
    # "gemma2:27b",
    # "qwen2.5:32b",
    # "mistral-small:22b"
]


detailed_prompt = """
Extract parameters for the following nanozymes from document:

1. "PCE(%)" : power conversion efficiency (%, numerical value)
2. "VOC(V)" : open-circuit voltage (V, numerical value)
3. "JSC(mA cm-2)" : short-circuit current density (mA/cm2, numerical value)
4. "FF(%)" : fill factor (%, numerical value)
5. "buried interface passivation agent" : chemical formula(s) of passivation agents applied before perovskite layer (on transport layer or in SnO2 solution). Multiple: comma-separated.
6. "perovskite layer additives" : chemical formula(s) of additives dissolved in perovskite precursor solution. Multiple: comma-separated.
7. "perovskite interface passivation agent" : chemical formula(s) of passivation agents applied after perovskite annealing. Multiple: comma-separated.

Rules:
- If a parameter is not found, use null.
- For passivation agents, output only chemical formulas (e.g., "PEAI", "KBr, PMMA").
- For electrical parameters, output numerical values (e.g., 19.5).

OUTPUT EXAMPLE (CSV format):
catalyst,PCE (%),VOC (V),JSC (mA cm-2),FF (%),buried interface passivation agent,perovskite layer additives,perovskite interface passivation agent
SnO2,19.5,1.08,22.3,78.5,KCl,FAI,PEAI
SnO2@KBr,21.2,1.12,23.5,80.1,KBr,MACl,PEAI, PMMA
"""


def extract_text_from_pdf(pdf_path: str) -> str:
    """从PDF文件中提取文本内容"""
    text = ""
    doc = fitz.open(pdf_path)
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


def extract_nanozyme_info(text: str, model: str) -> str:
    """调用Ollama模型提取纳米酶信息"""
    response = ollama.chat(
        model=model,
        messages=[
            {
                "role": "user",
                "content": detailed_prompt + "\n\nPlease extract nanozyme information from the following text:\n\n" + text
            }
        ]
    )
    return response["message"]["content"]


def save_csv(content: str, output_path: str) -> None:
    """保存CSV内容到文件"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)


def process_pdf(pdf_path: str, model: str, output_dir: str) -> None:
    """处理单个PDF文件"""
    print(f"正在处理: {pdf_path}")

    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        print(f"  警告: 无法从 {pdf_path} 提取文本")
        return

    result = extract_nanozyme_info(text, model)

    pdf_name = Path(pdf_path).stem

    csv_path = os.path.join(output_dir, f"{pdf_name}.csv")


    save_csv(result, csv_path)
    print(f"  已保存: {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="从PDF文献中提取纳米酶信息")
    parser.add_argument("pdf_dir", help="存放PDF文件的文件夹路径")

    args = parser.parse_args()

    pdf_dir = args.pdf_dir
    models = MODEL_LIST  # ? 用你定义的模型列表

    pdf_files = list(Path(pdf_dir).glob("*.pdf"))
    if not pdf_files:
        print(f"在 {pdf_dir} 中未找到PDF文件")
        return

    print(f"找到 {len(pdf_files)} 个PDF文件")
    print(f"将使用模型数量: {len(models)}")
    print("=" * 60)

    # ? 外层循环模型
    for model in models:
        print(f"\n?? 开始模型: {model}")

        # ? 每个模型一个文件夹
        output_dir = f"{model}_gtk_result"
        os.makedirs(output_dir, exist_ok=True)

        for pdf_path in pdf_files:
            try:
                process_pdf(str(pdf_path), model, output_dir)
            except Exception as e:
                print(f"  处理失败: {e}")

        print(f"? 模型 {model} 完成")

    print("\n?? 全部模型处理完成!")
if __name__ == "__main__":
    main()
