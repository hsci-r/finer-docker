import finer
from flask import Flask, request, Response

app = Flask(__name__)

@app.route('/', methods=['POST', 'GET'])
def index():
    text = request.values.get("text")
    pretokenized = request.values.get("pretokenized")
    if pretokenized != None:
       tokenize = False
    else:
       tokenize = True
    if text != None:
        result = ""
        for sentence in nertagger(text,tokenize):
            for word in sentence:
                result += word[0] + "\t" + word[1] + "\n"
            result += "\n"
        return Response(result, mimetype="text/plain")
    else:
        return Response("Error - You should provide the input text as 'text' GET/POST parameter", status=500, mimetype="text/plain")
        
nertagger = finer.Finer("/app/finnish-tagtools/tag") # pakollinen argumentti joka osoittaa FiNERin käyttämään datahakemistoon
print("FiNER ready and accepting connections.")
