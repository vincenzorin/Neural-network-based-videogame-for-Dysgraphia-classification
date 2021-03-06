# check GPU status:
#       watch -n 0.5 nvidia-smi

# Define options
class Options():
    pass
opt = Options()

# Training options
opt.batch_size = 50
opt.epochs = 100
opt.learning_rate = 0.001
opt.momentum = 0.9
opt.weight_decay = 5e-4

# Model options
opt.lstm_size = 128

# Backend options
opt.no_cuda = False

#Img options
opt.input_size = 50             #image height
opt.sequence_length = 150       #image lenght
opt.num_layers = 1

'''---------------------------------------------------'''

# Imports
import os, time, torch, sys
import torch.nn as nn
import torch.nn.functional as F
import torch.optim
import torch.backends.cudnn as cudnn; cudnn.benchmark = True
import torchvision.datasets as Datasets
import numpy as np
import lib.dysgrData as dysgrData
import lib.printTrack as pt
import lib.plotResult as plotResult
import csv

from torchvision.datasets import ImageFolder
from torchvision.transforms import ToTensor
from torch.utils.data.dataset import Dataset
from torch.utils.data import DataLoader
from torch.autograd import Variable
from lib.myDataset import myDatasetClass



# How to create datasets   util: https://discuss.pytorch.org/t/questions-about-imagefolder/774/3
DatabaseFeatures = dysgrData.loadFeatures()
if not DatabaseFeatures:
    print("There was a problem while loading features from db. Aborting now")
    sys.exit(0)

trainingResults = []
testResults = []

# full version dataset: 80.000 train, 20.000 test
img_dataset_train =  ImageFolder(root='img_train' , transform=ToTensor())
img_dataset_test =  ImageFolder(root='img_test' , transform=ToTensor())

# Wrapping custom Dataset
img_dataset_train = myDatasetClass(img_dataset_train)
img_dataset_test = myDatasetClass(img_dataset_test)
# Create loaders
dataset_train = torch.utils.data.DataLoader(dataset=img_dataset_train, batch_size=opt.batch_size, shuffle=True)
dataset_test = torch.utils.data.DataLoader(dataset=img_dataset_test, batch_size=opt.batch_size, shuffle=False)

if (len(dataset_train) and len(dataset_test)):
    print("Dataset loaded")

# Define model
class disModel(nn.Module):
    def __init__(self, input_size, hidden_size, num_layers):
        # Call parent
        super(disModel, self).__init__()
        # Set attributes
        self.is_cuda = False
        self.input_size = input_size
        self.lstm_size = opt.lstm_size
        self.linearOutput = 2                       #binary classification: 0 for dysgraphic, else 1

        # Define modules
        # INPUT IMG -> LSTM -> LINEAR -> SOFTMAX -> OUTPUT 
        self.lstm = nn.LSTM(input_size = self.input_size, hidden_size = self.lstm_size, 
                            num_layers = opt.num_layers, batch_first = True, 
                            dropout = 0, bidirectional = False)
        self.linear = nn.Linear(self.lstm_size,  self.linearOutput)
        
    def cuda(self):
        self.is_cuda = True
        super(disModel, self).cuda()

    def forward(self, x):
        pt.printTrack()            #print state

        # Compute lstm output
        output, _  = self.lstm(x)

        output = self.linear(output[:, -1, :])

        #output = torch.cat(output, 1)       #concat slope and time features just like this from csv
        
        # Compute softmax (commented if train method has his own loss opt)
        '''
        #output = F.log_softmax(output)
        #output = output.view(batch_size, output.size(1), -1)
        '''
        return output

myNN = disModel(opt.input_size, opt.lstm_size, opt.num_layers)
myNN.cuda()      #comment if we are not working with cuda

# Setup loss and optimizier
#criterion = lstm_softmax_loss           #this is custom, taken from daniele's example
criterion = nn.CrossEntropyLoss()
optimizer = torch.optim.Adam(myNN.parameters(), lr = opt.learning_rate)#, momentum = opt.momentum, weight_decay = opt.weight_decay)
#used ADAM instead Stochastic gradient descent (SGD)

train_correct = 0
train_total = 0
test_correct = 0
test_total = 0
for epoch in range(opt.epochs):
    train_loss = 0
    train_loss_cnt = 0
    #train phase here
    for i, (images, labels_cpu) in enumerate(dataset_train):
        images = Variable(images.cuda())
        labels = Variable(labels_cpu.cuda())
        
        optimizer.zero_grad()

        # Forward + Backward + Optimize
        outputs = myNN(images)

        # Compute loss (training only)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        _, predicted = torch.max(outputs.data, 1)              
        train_total += labels.size(0)
        train_correct += (predicted.cpu() == labels_cpu).sum()
        train_loss += loss.data[0]
        train_loss_cnt += 1

        #print and record train results
        if (i+1) % 100 == 0:
            print ('\rTraining: Epoch [%d/%d], Step [%d/%d], Loss: %.4f, Accuracy:  %d %%' 
                    %(epoch+1, opt.epochs, i+1, len(img_dataset_train)//opt.batch_size, train_loss/train_loss_cnt, 100 * train_correct / train_total))
            trainingResults.append((epoch+1, train_loss/train_loss_cnt, 100 * train_correct / train_total))

    test_loss_print = 0
    test_loss_cnt = 0
    #test phase here
    for i, (images, test_labels) in enumerate(dataset_test):
        images = Variable(images.cuda())
        outputs = myNN(images)
        test_loss = criterion(outputs, Variable(test_labels.cuda()))

        _, predicted = torch.max(outputs.data, 1)
        test_total += test_labels.size(0)
        test_correct += (predicted.cpu() == test_labels).sum()
        test_loss_print += loss.data[0]
        test_loss_cnt += 1
        
        #print and record test results
        if (i+1) % 25 == 0:
            print ('\rTesting Step [%d/%d], Loss: %.4f, Accuracy:  %d %%' 
                %(i+1, len(img_dataset_test)//opt.batch_size, test_loss_print/test_loss_cnt, 100 * test_correct / test_total))
            testResults.append((epoch+1, test_loss_print/test_loss_cnt, 100 * test_correct / test_total))

plotResult.plot(trainingResults, testResults)

# Save the Model
savingFile = "myNN.pkl"
print("Saving model as " + savingFile)
torch.save(myNN.state_dict(), savingFile)

# Save the results
try:
    with open("trainResults.txt", "w") as resultTrain: 
        csv_out=csv.writer(resultTrain)
        for line in trainingResults:
            csv_out.writerow(line)
    with open("testResults.txt", "w") as resultTest: 
        csv_out=csv.writer(resultTest)
        for line in testResults:
            csv_out.writerow(line)
finally:
    print("Done!")