import os 
import sys
import datetime 
from copy import deepcopy
import numpy as np 
import pandas as pd 
import wandb
from torch.utils.tensorboard import SummaryWriter 
from argparse import Namespace 
from .utils import plot_metric

class TensorBoardCallback:
    def __init__(self, save_dir= "runs", model_name="model", 
                 log_weight=False, log_weight_freq=5):
        self.__dict__.update(locals())
        nowtime = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_path = os.path.join(save_dir,model_name,nowtime)
        self.writer = SummaryWriter(self.log_path)
        
    def on_fit_start(self, model:'KerasModel'):
        
        #log weight
        if self.log_weight:
            net = model.accelerator.unwrap_model(model.net)
            for name, param in net.named_parameters():
                self.writer.add_histogram(name, param.clone().cpu().data.numpy(), 0)
            self.writer.flush()
        
    def on_train_epoch_end(self, model:'KerasModel'):
        
        epoch = max(model.history['epoch'])

        #log weight
        net = model.accelerator.unwrap_model(model.net)
        if self.log_weight and epoch%self.log_weight_freq==0:
            for name, param in net.named_parameters():
                self.writer.add_histogram(name, param.clone().cpu().data.numpy(), epoch)
            self.writer.flush()
        
    def on_validation_epoch_end(self, model:"KerasModel"):
        
        dfhistory = pd.DataFrame(model.history)
        epoch = max(model.history['epoch'])
        
        #log metric
        dic = deepcopy(dfhistory.loc[epoch-1])
        dic.pop("epoch")
        
        metrics_group = {}
        for key,value in dic.items():
            g = key.replace("train_",'').replace("val_",'')
            metrics_group[g] = dict(metrics_group.get(g,{}), **{key:value})
        for group,metrics in metrics_group.items():
            self.writer.add_scalars(group, metrics, epoch)
        self.writer.flush()
    
    
    def on_fit_end(self, model:"KerasModel"):
        
        #log weight 
        epoch = max(model.history['epoch'])
        if self.log_weight:
            net = model.accelerator.unwrap_model(model.net)
            for name, param in net.named_parameters():
                self.writer.add_histogram(name, param.clone().cpu().data.numpy(), epoch)
            self.writer.flush()
        self.writer.close()
        
        #save history
        dfhistory = pd.DataFrame(model.history)
        dfhistory.to_csv(os.path.join(self.log_path,'dfhistory.csv'),index=None)


class WandbCallback:
    def __init__(self, 
                 project = None,
                 config = None,
                 name = None,
                 save_ckpt = True,
                 save_code = True
                ):
        self.__dict__.update(locals())
        if isinstance(config,Namespace):
            self.config = config.__dict__ 
        if name is None:
            self.name =datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
    def on_fit_start(self, model:'KerasModel'):
        if wandb.run is None:
            wandb.init(project=self.project, config = self.config,
                   name = self.name, save_code=self.save_code)
        model.run_id = wandb.run.id
        
    def on_train_epoch_end(self, model:'KerasModel'):
        pass
    
    def on_validation_epoch_end(self, model:"KerasModel"):
        dfhistory = pd.DataFrame(model.history)
        epoch = max(dfhistory['epoch'])
        
        if epoch==1:
            for m in dfhistory.columns:
                wandb.define_metric(name=m, step_metric='epoch', hidden=False if m!='epoch' else True)
            wandb.define_metric(name='best_'+model.monitor,step_metric='epoch')
        
        dic = dict(dfhistory.loc[epoch-1])
        monitor_arr = dfhistory[model.monitor]
        best_monitor_score = monitor_arr.max() if model.mode=='max' else monitor_arr.min()
        dic.update({'best_'+model.monitor:best_monitor_score})
        wandb.run.summary["best_score"] = best_monitor_score
        wandb.log(dic)

    def on_fit_end(self, model:"KerasModel"):
        
        #save dfhistory
        dfhistory = pd.DataFrame(model.history)
        dfhistory.to_csv(os.path.join(wandb.run.dir,'dfhistory.csv'),index=None) 
        
        
        #save ckpt
        if self.save_ckpt:
            import shutil
            shutil.copy(model.ckpt_path,
                        os.path.join(wandb.run.dir,os.path.basename(model.ckpt_path)))
            
            arti_model = wandb.Artifact('checkpoint', type='model')
            arti_model.add_file(model.ckpt_path)
            wandb.log_artifact(arti_model)
            
                  
        #plotly metrics
        metrics = [x.replace('train_','').replace('val_','') for x in dfhistory.columns if 'train_' in x] 
        metric_fig = {m+'_curve':plot_metric(dfhistory,m) for m in metrics}
        wandb.log(metric_fig)
        wandb.finish()
        
class MiniLogCallback:
    def __init__(self, ):
        pass

    def on_fit_start(self, model:'KerasModel'):
        pass
        
    def on_train_epoch_end(self, model:'KerasModel'):
        pass
    
    def on_validation_epoch_end(self, model:"KerasModel"):
        dfhistory = pd.DataFrame(model.history)
        epoch = max(dfhistory['epoch'])
        monitor_arr = dfhistory[model.monitor]
        best_monitor_score = monitor_arr.max() if model.mode=='max' else monitor_arr.min()
        
        nowtime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"epoch【{epoch}】@{nowtime} --> best_{model.monitor} = {str(best_monitor_score)}",
              file = sys.stderr, end = '\r')
        
    def on_fit_end(self, model:"KerasModel"):
        pass