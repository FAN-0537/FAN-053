import configparser

from openai import OpenAI

cfg = configparser.ConfigParser()
cfg.read("config.ini", encoding="utf-8")

client = OpenAI(api_key=cfg["llm"]["api_key"], base_url=cfg["llm"]["base_url"])

question = input("\n你: ").strip()

print("\nAI: ", end="", flush=True)
for chunk in client.chat.completions.create(
    model=cfg["llm"]["model"],
    temperature=float(cfg["llm"]["temperature"]),
    messages=[{"role": "user", "content": question}],
    stream=True,
):
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print("\n---")
