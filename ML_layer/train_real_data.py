import pandas as pd
import urllib.request
import zipfile
import os
import pickle
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split

# 1. Download the Real UCI Incident Dataset
url = "https://archive.ics.uci.edu/ml/machine-learning-databases/00498/incident_event_log.zip"
zip_path = "incident_event_log.zip"
csv_path = "incident_event_log.csv"

if not os.path.exists(csv_path):
    print("Downloading dataset from UCI Machine Learning Repository...")
    urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(".")
    print("Download complete.")

# 2. Load and Clean the Data
print("Loading data...")
df = pd.read_csv(csv_path)

# Filter out closed/resolved tickets to only train on initial alert states
df = df[df['incident_state'].isin(['New', 'Active'])]

# Select features we care about for routing
features = ['category', 'subcategory', 'u_symptom']
target = 'priority' # Predicts "1 - Critical", "2 - High", etc.

# Drop missing values
df = df[features + [target]].dropna()

# 3. Encode Categorical Data
print("Encoding features...")
encoders = {}
for col in features:
    le = LabelEncoder()
    df[col] = le.fit_transform(df[col].astype(str))
    encoders[col] = le

X = df[features]
y = df[target]

# 4. Train the Random Forest
print("Training Random Forest Classifier (this takes ~5-10 seconds)...")
clf = RandomForestClassifier(n_estimators=50, max_depth=10, random_state=42, n_jobs=-1)
clf.fit(X, y)

# 5. Save the Model
with open("ml_model.pkl", "wb") as f:
    pickle.dump({"model": clf, "encoders": encoders, "features": features}, f)

print("✅ Model trained on REAL UCI data and saved to 'ml_model.pkl'!")
