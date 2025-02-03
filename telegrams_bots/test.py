import pickle

with open('bot_data.pkl', 'rb') as file:
    data = pickle.load(file)
print(data)