# Use uma imagem base Python
FROM python:3.9

# Defina o diretório de trabalho como /app
WORKDIR /app

# Copie o arquivo requirements.txt para o diretório de trabalho
COPY requirements.txt .

# Instale as dependências do projeto
RUN pip install --no-cache-dir -r requirements.txt

# Copie o código fonte para o diretório de trabalho
COPY . .

# Exponha a porta 5000 para acessar a aplicação Flask
EXPOSE 5000

# Execute o comando para iniciar a aplicação
CMD ["python", "app.py"]
