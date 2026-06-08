#!/usr/bin/env python3
# dashboard/app.py - Servidor Flask
# Ejecutar: python app.py

import csv
from pathlib import Path
from flask import Flask, render_template, jsonify
from collections import defaultdict
from datetime import datetime

app = Flask(__name__)

STATUS_FILE = Path(__file__).parent.parent / "data" / "estado.csv"

def cargar_datos():
    if not STATUS_FILE.exists():
        return []
    datos = []
    with open(STATUS_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            datos.append(row)
    return datos

def get_stats(datos):
    total = len(datos)
    enviados = sum(1 for r in datos if r.get('enviado', '').upper() == 'SI')
    con_web = sum(1 for r in datos if r.get('project_path'))
    con_link = sum(1 for r in datos if r.get('live_url'))
    return {
        'total': total,
        'enviados': enviados,
        'con_web': con_web,
        'con_link': con_link,
        'tasa_envio': round(enviados/total*100, 1) if total else 0,
        'tasa_web': round(con_web/enviados*100, 1) if enviados else 0,
        'tasa_deploy': round(con_link/con_web*100, 1) if con_web else 0,
    }

def get_categorias(datos):
    cats = defaultdict(lambda: {'total': 0, 'enviados': 0, 'con_link': 0})
    for r in datos:
        cat = r.get('categoria', 'General')
        cats[cat]['total'] += 1
        if r.get('enviado', '').upper() == 'SI':
            cats[cat]['enviados'] += 1
        if r.get('live_url'):
            cats[cat]['con_link'] += 1
    resultado = []
    for cat, data in cats.items():
        resultado.append({
            'nombre': cat,
            'total': data['total'],
            'enviados': data['enviados'],
            'convertidos': data['con_link'],
            'tasa_envio': round(data['enviados']/data['total']*100, 1) if data['total'] else 0,
        })
    return sorted(resultado, key=lambda x: -x['total'])[:6]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/datos')
def api_datos():
    datos = cargar_datos()
    stats = get_stats(datos)
    categorias = get_categorias(datos)
    return jsonify({
        'stats': stats,
        'categorias': categorias,
        'leads': datos,
        'lastUpdated': datetime.now().isoformat()
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)