import os
import argparse
import pickle
import numpy as np
import pandas as pd
import networkx as nx
import keras
from keras import optimizers, losses, layers, metrics
from sklearn import preprocessing, feature_extraction, model_selection
from keras.layers import Dropout

import stellargraph as sg
from stellargraph.layer import GCN, GraphConvolution
from stellargraph.mapper import FullBatchNodeGenerator, GCN_A_feats


def train(train_nodes,
            train_targets,
            val_nodes,
            val_targets,
            generator,
            dropout=0.0,
            layer_sizes=[16, 7],
            learning_rate = 0.01,
            activations = ['relu', 'softmax']):

    train_gen = generator.flow(train_nodes, train_targets)
    val_gen = generator.flow(val_nodes, val_targets)
    gcnModel = GCN(layer_sizes, activations, generator=generator, bias=True, dropout=dropout)

    # Expose the input and output sockets of the model:
    x_inp, x_out = gcnModel.node_model()

    # Create Keras model for training
    model = keras.Model(inputs=x_inp, outputs=x_out)
    model.compile(loss=losses.categorical_crossentropy, weighted_metrics=[metrics.categorical_accuracy], optimizer=optimizers.Adam(lr=learning_rate))

    # Train model
    history = model.fit_generator(
        train_gen, epochs=100, validation_data=val_gen, verbose=2, shuffle=False
    )

    return model



def test(test_nodes, test_targets, generator, model_file, model):
    test_gen = generator.flow(test_nodes, test_targets)

    model = keras.models.load_model(model_file, custom_objects={"GraphConvolution": GraphConvolution})
    model.compile(loss=losses.categorical_crossentropy, weighted_metrics=[metrics.categorical_accuracy], optimizer=optimizers.Adam(lr=0.01))
    print(model.summary())

    # Evaluate on test set and print metrics
    test_metrics = model.evaluate_generator(test_gen)

    for name, val in zip(model.metrics_names, test_metrics):
        print("\t{}: {:0.4f}".format(name, val))


edgelist = pd.read_table(
    os.path.join('data/cora', 'cora.cites'), header=None, names=['source', 'target']
)

# Load node features
# The CORA dataset contains binary attributes 'w_x' that correspond to whether the corresponding keyword
# (out of 1433 keywords) is found in the corresponding publication.
feature_names = ['w_{}'.format(ii) for ii in range(1433)]
# Also, there is a "subject" column
column_names = feature_names + ['subject']
node_data = pd.read_table(
    os.path.join('data/cora', 'cora.content'), header=None, names=column_names
)

target_encoding = feature_extraction.DictVectorizer(sparse=False)
node_targets = target_encoding.fit_transform(
    node_data[['subject']].to_dict("records")
)

node_ids = node_data.index
node_features = node_data[feature_names]

Gnx = nx.from_pandas_edgelist(edgelist)

# Convert to StellarGraph and prepare for ML
G = sg.StellarGraph(Gnx, node_type_name="label", node_features=node_features)

# Split nodes into train/test using stratification.
train_nodes, test_nodes, train_targets, test_targets = model_selection.train_test_split(
    node_ids, node_targets, train_size=140, test_size=None, stratify=node_targets, random_state=55232
)

# Split test set into test and validation
val_nodes, test_nodes, val_targets, test_targets = model_selection.train_test_split(
    test_nodes, test_targets, train_size=300, test_size=None, random_state=523214
)

generator = FullBatchNodeGenerator(G, func_opt=GCN_A_feats, filter='localpool')

dropout=0.0
layer_sizes=[16, 7]
learning_rate = 0.01
activations = ['relu', 'softmax']

model = train(train_nodes, train_targets, val_nodes, val_targets, generator, dropout,
    layer_sizes, learning_rate, activations)

# Save the trained model
save_str = "_h{}_l{}_d{}_r{}".format(
    "gcn", ''.join([str(x) for x in layer_sizes]), str(dropout), str(learning_rate)
)

model.save("cora_gcn_model" + save_str + ".h5")

# We must also save the target encoding to convert model predictions
with open("cora_gcn_encoding" + save_str + ".pkl", "wb") as f:
    pickle.dump([target_encoding], f)

test(test_nodes, test_targets, generator, "cora_gcn_model" + save_str + ".h5", learning_rate)
