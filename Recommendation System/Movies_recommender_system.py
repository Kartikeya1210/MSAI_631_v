import pandas as pd
import numpy as np
import random
import matplotlib.pyplot as plt
import time
import re
from surprise import Reader, Dataset, SVD, dump
from surprise.model_selection import cross_validate
from pymongo import MongoClient

############################################################
# Data loading
############################################################
# Load movie catalogue
df_mov_titles = pd.read_csv('C:/Users/Kartikeya Shah/Desktop/Projects/MSAI_631/Recommendation System/Kartikeya/Recommendation_System/data/movie_titles.csv', sep=',', header=None, names=['Movie_Id', 'Year', 'Name'],
                            usecols=[0,1,2], encoding="ISO-8859-1")
df_mov_titles.set_index('Movie_Id', inplace = True)

print('Movies catalogue shape: {}'.format(df_mov_titles.shape))
print(df_mov_titles.head(10))

# Load files with ratings in a loop
_files = ['./data/combined_data_1.txt','./data/combined_data_2.txt','./data/combined_data_3.txt','./data/combined_data_4.txt']
df_ratings = pd.DataFrame()

for _f in _files:
    _staging = pd.read_csv('C:/Users/Kartikeya Shah/Desktop/Projects/MSAI_631/Recommendation System/Kartikeya/Recommendation_System/data/clients_data.csv', header = None, names = ['Cust_Id', 'Rating'], usecols = [0,1])
    _staging['Rating'] = _staging['Rating'].astype(float)
    print("{} shape: {}".format(_f, _staging.shape))
    
    if len(df_ratings) > 0:
        df_ratings = pd.concat([df_ratings, _staging], ignore_index=True)
    else:
        df_ratings = _staging
    del _staging
    
print('Tot shape: {}'.format(df_ratings.shape))
print(df_ratings.head())

############################################################
# Data wrangling
############################################################
# Prepare data to place movie id on the columns. (Movie ID is currently a row, where Rating is NaN)

## Create a dataframe keeping the records where the rating is NaN
movies_IDs = pd.DataFrame(pd.isnull(df_ratings.Rating))
movies_IDs = movies_IDs[movies_IDs['Rating'] == True]
movies_IDs = movies_IDs.reset_index() # since movies are in order, we can reset the indexes

## Zip creates tuples: e.g. (548, 0), i.e. at row 548 we have the 1st movie, then from row 548 till 694 the 2nd, etc.
movies_IDs_fin = []
mo = 1 # first movie ID
for i,j in zip(movies_IDs['index'][1:],movies_IDs['index'][:-1]):
    temp = np.full((1,i-j-1), mo) # create an array of size i-j-1 with value mo repeated
    movies_IDs_fin = np.append(movies_IDs_fin, temp)
    mo += 1
## Handle last record (which require len(df_ratings))
last_ = np.full((1,len(df_ratings) - movies_IDs.iloc[-1, 0] - 1), mo)
movies_IDs_fin = np.append(movies_IDs_fin, last_)

print('Movie IDs array shape: {}'.format(movies_IDs_fin.shape))

# Remove rows where rating is NaN and place moviedID as a new column
df_ratings = df_ratings[pd.notnull(df_ratings['Rating'])]

df_ratings['Movie_Id'] = movies_IDs_fin.astype(int)
del movies_IDs_fin
df_ratings['Cust_Id'] = df_ratings['Cust_Id'].astype(int)

print('Tot shape: {}'.format(df_ratings.shape))
print('Tot clients: {}'.format(len(df_ratings['Cust_Id'].unique())))
print(df_ratings.head(3))

############################################################
# Export a data sample
############################################################
num_clients = 32013 # obtained dividing the full client len (480'189) by 15
num_movies = 1300 # obtained dividing the full movie len (17'770) by 15
w_ = [.01, .01, .08, .90] # weights to pick records by quartile, i.e. 1% of clients/movies will be picked by bottom .25 quartile
q_ = [.25, .5, .75, 1.]
random.seed(33)

# Mark movies deciles
movie_summary = df_ratings.groupby('Movie_Id').agg(reviews_count=('Rating','count'))
percentiles_ = np.linspace(0,1,11) # i.e. deciles, labelling each record with the decile it falls into
movie_summary['deciles'] = pd.qcut(movie_summary.reviews_count, percentiles_, labels=percentiles_[:-1])
movie_summary['deciles'] = movie_summary['deciles'].astype('float')
movie_summary.reset_index(inplace=True)
print(movie_summary.head(3))

# Mark customers deciles
cust_summary = df_ratings.groupby('Cust_Id').agg(reviews_count=('Rating','count'))
percentiles_ = np.linspace(0,1,11)
cust_summary['deciles'] = pd.qcut(cust_summary.reviews_count, percentiles_, labels=percentiles_[:-1])
cust_summary['deciles'] = cust_summary['deciles'].astype('float')
cust_summary.reset_index(inplace=True)
print(cust_summary.head(3))

# Pick IDs
movies_IDs = []
cust_IDs = []

qprev = 0.
for i in range(len(w_)):
    mo = random.sample(list(movie_summary.loc[(movie_summary['deciles']>qprev)&(movie_summary['deciles']<=q_[i]), "Movie_Id"]),
                      round(num_movies*w_[i]))
    cus = random.sample(list(cust_summary.loc[(cust_summary['deciles']>qprev)&(cust_summary['deciles']<=q_[i]), "Cust_Id"]),
                       round(num_clients*w_[i]))
    for m in mo:
        movies_IDs.append(m)
    for c in cus:
        cust_IDs.append(c)
    qprev = q_[i] #update previous quantile for next iteration

print("Selected {} movies".format(len(movies_IDs)))
print("Selected {} customers".format(len(cust_IDs)))

# Filter main df
print('Original shape: {}'.format(df_ratings.shape))
df_ratings_XS = df_ratings[df_ratings['Movie_Id'].isin(movies_IDs)]
df_ratings_XS = df_ratings_XS[df_ratings_XS['Cust_Id'].isin(cust_IDs)]
print('After filtering shape: {}'.format(df_ratings_XS.shape))

# Export filtered df
df_ratings_XS.to_csv('C:/Users/Kartikeya Shah/Desktop/Projects/MSAI_631/Recommendation System/Kartikeya/Recommendation_System/data/df_ratings_XS.zip', header=True, index=False, sep='|', mode='w',
                    compression={'method': 'zip', 'compresslevel': 9})

############################################################
# Model
############################################################
reader = Reader()
data = Dataset.load_from_df(df_ratings_XS[['Cust_Id', 'Movie_Id', 'Rating']][:], reader)

## Tuning the nr of factors
minrmse_ = []; maxrmse_ = []; avgrmse_ = []
f_ = []
for f in range(20, 201, 20):
    svd_ = SVD(biased=False, n_factors=f)
    res_ = cross_validate(svd_, data, measures=['RMSE'], cv=5, n_jobs=-1)
    f_.append(f)
    minrmse_.append(res_['test_rmse'].min())
    avgrmse_.append(res_['test_rmse'].mean())
    maxrmse_.append(res_['test_rmse'].max())

plt.style.use('ggplot')
plt.figure(figsize = (6,4))
plt.plot(f_, avgrmse_, marker = 'o', linewidth = 3, color='blue', label='Avg RMSE')
plt.plot(f_, minrmse_, marker = 'o', linewidth = 2, linestyle='--', color='green', label='Min RMSE')
plt.plot(f_, maxrmse_, marker = 'o', linewidth = 2, linestyle='--', color='orange', label='Max RMSE')
plt.xlabel('Factor')
plt.ylabel('RMSE')
plt.grid(visible=True)
plt.title("SVD 5-fold CV RMSE depending on factor")
plt.legend(loc='lower right')
plt.show()

# Final model
svd = SVD(biased=False, n_factors=80)
res = cross_validate(svd, data, measures=['RMSE'], cv=5, n_jobs=-1)
print(res)
dump.dump(file_name = "C:/Users/Kartikeya Shah/Desktop/Projects/MSAI_631/Recommendation System/Kartikeya/Recommendation_System/svd_model", algo = svd, verbose = 1) # Save model to file

# Obtain U and V matrix from SVD formulas
data_ = data.build_full_trainset()
svd.fit(data_)
U_ = svd.pu
V_ = svd.qi
print(U_.shape)
print(V_.shape)

############################################################
# Predictions for a customer
############################################################
_Custid = 1765963

# Real ratings
real_ratings = df_ratings_XS.loc[df_ratings_XS['Cust_Id']==_Custid, :]
real_ratings = pd.merge(left=real_ratings.set_index(['Movie_Id']), right=df_mov_titles['Name'],
                        how='left', left_index=True, right_index=True)
print(real_ratings.sort_values(by=['Rating'], ascending=[False]).head(20))

# Predict ratings for movies with no ratings
pred_data = []
movieids = np.sort(df_ratings_XS['Movie_Id'].unique())
to_rate = [mo for mo in movieids if mo not in list(df_ratings_XS.loc[df_ratings_XS['Cust_Id']==_Custid, 'Movie_Id'])]
for mo in to_rate:
    pred_data.append([mo, _Custid, svd.predict(_Custid, mo).est])
pred_ratings = pd.DataFrame(data=pred_data, columns=['Movie_Id', 'Cust_Id', 'Predicted_Rating'])
pred_ratings = pd.merge(left=pred_ratings.set_index(['Movie_Id']), right=df_mov_titles['Name'],
                        how='left', left_index=True, right_index=True)
print(pred_ratings.sort_values(by=['Predicted_Rating','Name'], ascending=[False,True]).head(20))

############################################################
# Predictions for all users and movies
############################################################
## Create predictions for all movies and users
st = time.time()
preds_ = []
movieids = np.sort(df_ratings_XS['Movie_Id'].unique())
userids = np.sort(df_ratings_XS['Cust_Id'].unique())

for mo in movieids:
    preds_.append([svd.predict(cc,mo).est for cc in userids])

elapsed_ = time.strftime("%Hh%Mm%Ss", time.gmtime(time.time()-st))
print("Predictions completed in: {}".format(elapsed_))

## Transform predictions into dataframe only for missing ratings
st = time.time()

# Identify movies rated already
df_ratings_XS['K'] = df_ratings_XS['Cust_Id'].astype(str)+'_'+df_ratings_XS['Movie_Id'].astype(str)
Keys_rated = df_ratings_XS['K'].unique()
Keys_rated = set(Keys_rated)

# Identify missing ratings
preds_df_data = []
for i in range(len(preds_)):
    for j in range(len(preds_[i])):
        if str(userids[j])+'_'+str(movieids[i]) not in Keys_rated:
            preds_df_data.append([movieids[i], userids[j], preds_[i][j]])
preds_df = pd.DataFrame(data=preds_df_data, columns=['Movie_Id', 'Cust_Id', 'Predicted_Rating'])

elapsed_ = time.strftime("%Hh%Mm%Ss", time.gmtime(time.time()-st))
print("Dataframe creation completed in: {}".format(elapsed_))

print(preds_df.head(3))

############################################################
# Create extra fields for movies and users
############################################################
# Add an URL to movies
url_ = "https://www.youtube.com/results?search_query="
Links_ = list(df_mov_titles['Name'])
for i in range(0, len(Links_)):
    new_ = re.sub(r"[^\w\s]", '', Links_[i])
    new_ = re.sub(r"\s+", '+', new_)
    Links_[i] = url_+new_+"+official+trailer"

df_mov_titles['Link'] = Links_
# display(df_mov_titles.head(3))
print(df_mov_titles.head(3))

df_mov_titles.to_csv('C:/Users/Kartikeya Shah/Desktop/Projects/MSAI_631/Recommendation System/Kartikeya/Recommendation_System/data/movie_titles_v2.csv', header=True, index=True, sep='|', mode='w')
df_mov_titles2 = pd.read_csv('C:/Users/Kartikeya Shah/Desktop/Projects/MSAI_631/Recommendation System/Kartikeya/Recommendation_System/movie_titles_v2.csv', sep='|', header=0, usecols=[0,1,2,3], 
                             encoding="ISO-8859-1", dtype={'Year':'str', 'Name':'str', 'Link':'str'})
df_mov_titles2.set_index('Movie_Id', inplace = True)

# Add simulated name, surname, email to users
file = 'Common_names.xlsx'
first_names_ = pd.read_excel(io = 'C:/Users/Kartikeya Shah/Desktop/Projects/MSAI_631/Recommendation System/Kartikeya/Recommendation_System/data/clients_data.csv', sheet_name='First_names')
first_names_ = list(first_names_['First Name'])
last_names_ = pd.read_excel(io = 'C:/Users/Kartikeya Shah/Desktop/Projects/MSAI_631/Recommendation System/Kartikeya/Recommendation_System/data/clients_data.csv', sheet_name='Last_names')
last_names_ = list(last_names_['Last Name'])
domains_ = pd.read_excel(io = 'C:/Users/Kartikeya Shah/Desktop/Projects/MSAI_631/Recommendation System/Kartikeya/Recommendation_System/data/clients_data.csv', sheet_name='Domains')
domains_ = list(domains_['Domain Name'])

unique_cl = set()
data_cl = []
userids = df_ratings_XS['Cust_Id'].unique()

for cc in userids:
    isunique = 'N'
    while isunique == 'N':
        fn = random.sample(first_names_, 1)[0]
        ln = random.sample(last_names_, 1)[0]
        if str(fn+' '+ln) not in unique_cl:
            isunique = 'Y'
            unique_cl.add(str(fn+' '+ln))
    dom = random.sample(domains_, 1)[0]
    email = str(fn+'.'+ln+'@'+dom).lower()
    data_cl.append([cc, fn, ln, email])

data_cl_df = pd.DataFrame(data=data_cl, columns=['Cust_Id', 'First_Name', 'Last_Name', 'Email'])

print(data_cl_df.head())
print(len(data_cl_df))
data_cl_df.to_csv('C:/Users/Kartikeya Shah/Desktop/Projects/MSAI_631/Recommendation System/Kartikeya/Recommendation_System/data/clients_data.csv', header=True, index=False, sep='|', mode='w')

############################################################
# MongoDB
############################################################
# Connection to local
client = MongoClient('mongodb://localhost:27017/admin?retryWrites=true&w=majority')

# Save into collections
db = client['recommender_system']

def write_data(coll_name, df_):
    st = time.time()
    collection = db[coll_name]
    st_ = collection.count_documents({})
    to_upload = df_.to_dict('records')
    collection.insert_many(to_upload)
    end_ = collection.count_documents({})
    elapsed_ = time.strftime("%Hh%Mm%Ss", time.gmtime(time.time()-st))
    print("{} documents inserted into {}\nData upload completed in {}\n".format(str(end_-st_), coll_name, elapsed_))

write_data('users', data_cl_df)
write_data('movies', df_mov_titles2.reset_index())
write_data('ratings', df_ratings_XS.loc[:, ['Cust_Id','Rating','Movie_Id']])
write_data('predictions', preds_df)
