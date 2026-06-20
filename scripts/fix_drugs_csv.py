from pathlib import Path

p = Path("data/samples/drugs.csv")
lines = p.read_text(encoding="utf-8").splitlines()
lines[-1] = (
    "\u0421\u043f\u0438\u0440\u043e\u043d\u043e\u043b\u0430\u043a\u0442\u043e\u043d,"
    '"\u041a\u0430\u043b\u0438\u0439\u0441\u0431\u0435\u0440\u0435\u0433\u0430\u044e\u0449\u0438\u0439 \u0434\u0438\u0443\u0440\u0435\u0442\u0438\u043a.",'
    '"25 \u043c\u0433"'
)
p.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("fixed")
