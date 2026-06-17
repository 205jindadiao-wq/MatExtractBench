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
    #
    # "qwen2.5:7b",
    # "deepseek-r1:14b",
    #
    #"dolphin3:8b",
    #"glm4:9b",
    #"gemma:7b",
    #"llava-llama3:8b",
    #"mistral-nemo:12b",
    #"openthinker:7b",
    #"qwen2.5:14b",
    #"deepseek-v2:16b",
    #"granite3.3:8b",
    #"gemma2:9b",
    #"mistral:7b",
    #"deepseek-r1:7b",
    #"deepseek-r1:1.5b",
    #"llama3.1:8b",
    #"deepseek-r1:14b",
    #"qwen2.5:7b",
    #"qwen2:7b",
    #"llama3:8b",
    "deepseek-r1:32b",
    # "openthinker:32b",
    # "gemma2:27b",
    # "qwen2.5:32b",
    # "mistral-small:22b"
]


detailed_prompt = """
        Extract comprehensive information about all nanozymes from the knowledge base and provide structured data according to the following requirements:

        REQUIREMENTS:
        1. Directly output all materials identified as nanozymes 
        2. Classification: Specify which enzyme class each nanozyme belongs to:
           - CAT (Catalase)
           - HYL (Hydrolase) 
           - OXD (Oxidase)
           - POD (Peroxidase)
           - SOD (Superoxide Dismutase)
        3. Elemental composition: For each nanozyme, identify presence (1) or absence (0) of the following elements:
           - O, N, P, S, Si, Se, B, F, Cl, Br, I
        4. Primary metal oxidation state: Identify the oxidation state of the main metal element in each nanozyme
        5. Physical properties:
           - Shape
           - Size (nm)
           - Surface treatment/functionalization
           - Dispersion medium
        6. Enzymatic properties:
           - Optimal pH
           - Optimal reaction temperature (C)
           - Substrate
           - Michaelis constant Km (mM)
           - Maximum reaction rate Vmax (uM s-1)
           - Turnover number Kcat (s-1)

        Present all information in a structured tabular format, ensuring each parameter corresponds precisely to each nanozyme.

STRICT OUTPUT RULES:
- Output ONLY CSV content, no explanations
- Do NOT include markdown formatting
- Do NOT include units in numeric fields (units already defined in header)
- Use "Unknown" for missing values
- Ensure all rows strictly follow the header order
- If multiple nanozymes are found, output multiple rows

OUTPUT EXAMPLE (CSV format):
nanozyme,classification,contain O,contain N,contain P,contain S,contain Si,contain Se,contain B,contain F,contain Cl,contain Br,contain I,main metal oxidation state,shape,size (nm),surface treatment,dispersion medium,pH,temperature/oC,Substrate,Km/mM,Vmax/μM s-1,Kcat/s-1
Fe3O4 nanoparticles,POD,1,0,0,0,0,0,0,0,0,0,0,+2/+3,spherical,50,PEGylation,water,4.5,37,TMB,0.12,85.3,120.5
CeO2 nanorods,SOD,1,0,0,0,0,0,0,0,0,0,0,+3/+4,rod,120,None,buffer solution,7.4,25,superoxide,0.08,60.2,95.1
Au@Pt core-shell nanoparticles,OXD,0,0,0,0,0,0,0,0,0,0,0,0,spherical,30,PVP coating,water,6.8,30,glucose,Unknown,Unknown,Unknown
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
        output_dir = f"{model}_nmm_result"
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
