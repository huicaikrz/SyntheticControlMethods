from __future__ import absolute_import, division, print_function

import pandas as pd
import numpy as np

from synth.plot import Plot
from synth.inferences import Inferences

class SynthBase(Inferences, Plot): #inferences, plot
    
    def __init__(self, dataset, outcome_var, id_var, time_var, treatment_period, treated_unit, 
                covariates, periods_all, periods_pre_treatment, n_controls, n_covariates,
                treated_outcome, control_outcome, treated_covariates, control_covariates,
                treated_outcome_all, control_outcome_all,
                treatment_effect=None, w=None, **kwargs):

        '''
        INPUT VARIABLES:
        
        dataset: the dataset for the synthetic control procedure.
        Should have the the following column structure:
        ID, Time, outcome_var, x0, x1,..., xn
        Each row in dataset represents one observation.
        The dataset should be sorted on ID then Time. 
        That is, all observations for one unit in order of Time, 
        followed by all observations by the next unit also sorted on time
        
        ID: a string containing a unique identifier for the unit associated with the observation.
        E.g. in the simulated datasets provided, the ID of the treated unit is "A".
        
        Time: an integer indicating the time period to which the observation corresponds.
        
        treated_unit: ID of the treated unit
        
        treatment_effect:
        '''


        
        self.dataset = dataset
        self.y = outcome_var
        self.id = id_var
        self.time = time_var
        self.treatment_period = treatment_period
        self.treated_unit = treated_unit
        self.covariates = covariates
        self.periods_all = periods_all
        self.periods_pre_treatment = periods_pre_treatment
        self.n_controls = n_controls
        self.n_covariates = n_covariates        
        
        '''
        PROCESSED VARIABLES:
        
        treated_outcome: a (1 x treatment_period) matrix containing the
        outcome of the treated unit for each observation in the pre-treatment period.
        Referred to as Z1 in Abadie, Diamond, Hainmueller.
        
        control_outcome: a ((len(unit_list)-1) x treatment_period) matrix containing the
        outcome of every control unit for each observation in the pre-treatment period
        Referred to as Z0 in Abadie, Diamond, Hainmueller.
        
        treated_outcome_all: a (1 x len(time)) matrix
        same as treated_outcome but includes all observations, including post-treatment
        
        control_outcome_all: a (n_controls x len(time)) matrix
        same as control_outcome but includes all observations, including post-treatment
        
        treated_covariates: a (1 x len(covariates)) matrix containing the
        average value for each predictor of the treated unit in the pre-treatment period
        Referred to as X1 in Abadie, Diamond, Hainmueller.
        
        control_covariates: a (n_controls x len(covariates)) matrix containing the
        average value for each predictor of every control unit in the pre-treatment period
        Referred to as X0 in Abadie, Diamond, Hainmueller.
        
        W: a (1 x n_controls) matrix containing the weights assigned to each
        control unit in the synthetic control. W is contstrained to be convex,
        that is sum(W)==1 and ∀w∈W, w≥0, each weight is non-negative and all weights sum to one.
        Referred to as W in Abadie, Diamond, Hainmueller.
        
        V: a (len(covariates) x len(covariates)) matrix representing the relative importance
        of each covariate. V is contrained to be diagonal, positive semi-definite. 
        Pracitcally, this means that the product V.control_covariates and V.treated_covariates
        will always be non-negative. Further, we constrain sum(V)==1, otherwise there will an infinite
        number of solutions V*c, where c is a scalar, that assign equal relative importance to each covariate
        Referred to as V in Abadie, Diamond, Hainmueller.
        '''

        self.treated_outcome = treated_outcome
        self.control_outcome = control_outcome
        self.treated_covariates = treated_covariates
        self.control_covariates = control_covariates
        self.treated_outcome_all = treated_outcome_all
        self.control_outcome_all = control_outcome_all

        self.w = w #Can be provided if using Synthetic DID
        self.v = None
        self.fail_count = 0 #Used to limit number of optimization attempts
        self.treatment_effect = treatment_effect #If known

    
class Synth(SynthBase):

    def __init__(self, dataset, outcome_var, id_var, time_var, treatment_period, treated_unit, **kwargs):
        checked_input = self._process_input_data(
            dataset, outcome_var, id_var, time_var, treatment_period, treated_unit, **kwargs
        )
        super(Synth, self).__init__(**checked_input)
        #fit model
        #process results
        '''
        self.model_args = checked_input['model_args']
        self.model = checked_input['model']
        self._fit_model()
        self._process_posterior_inferences()
        '''

    
    def _process_input_data(self, dataset, outcome_var, id_var, time_var, treatment_period, treated_unit, **kwargs):
        '''
        Extracts processed variables, excluding v and w, from input variables.
        These are all the data matrices.
        '''
        #All columns not y, id or time must be predictors
        covariates = [col for col in dataset.columns if col not in [outcome_var, id_var, time_var]]

        #Extract quantities needed for pre-processing matrices
        #Get number of periods in pre-treatment and total
        periods_all = dataset[time_var].nunique()
        periods_pre_treatment = dataset.loc[dataset[time_var]<treatment_period][time_var].nunique()
        #Number of control units, -1 to remove treated unit
        n_controls = dataset[id_var].nunique() - 1
        n_covariates = len(covariates)

        ###Get treated unit matrices first###
        treated_outcome_all, treated_outcome, treated_covariates = self._process_treated_data(
            dataset, outcome_var, id_var, time_var, 
            treatment_period, treated_unit, periods_all, 
            periods_pre_treatment, covariates, n_covariates
        )
        
        ### Now for control unit matrices ###
        control_outcome_all, control_outcome, control_covariates = self._process_control_data(
            dataset, outcome_var, id_var, time_var, 
            treatment_period, treated_unit, n_controls, 
            periods_all, periods_pre_treatment, covariates
        )

        return {
            'dataset': dataset,
            'outcome_var':outcome_var,
            'id_var':id_var,
            'time_var':time_var,
            'treatment_period':treatment_period,
            'treated_unit':treated_unit,
            'covariates':covariates,
            'periods_all':periods_all,
            'periods_pre_treatment':periods_pre_treatment,
            'n_controls': n_controls,
            'n_covariates':n_covariates,
            'treated_outcome_all': treated_outcome_all,
            'treated_outcome': treated_outcome,
            'treated_covariates': treated_covariates,
            'control_outcome_all': control_outcome_all,
            'control_outcome': control_outcome,
            'control_covariates': control_covariates,
        }
    
    def _process_treated_data(self, dataset, outcome_var, id_var, time_var, treatment_period, treated_unit, 
                            periods_all, periods_pre_treatment, covariates, n_covariates):
        '''
        Extracts..
        '''

        treated_data_all = dataset[dataset[id_var] == treated_unit]
        treated_outcome_all = np.array(treated_data_all[outcome_var]).reshape(periods_all,1) #All outcomes
        
        #Only pre-treatment
        treated_data = treated_data_all[dataset[time_var] < treatment_period]
        #Extract outcome and shape as matrix
        treated_outcome = np.array(treated_data[outcome_var]).reshape(periods_pre_treatment, 1)
        #Columnwise mean of each covariate in pre-treatment period for treated unit, shape as matrix
        treated_covariates = np.array(treated_data[covariates].mean(axis=0)).reshape(n_covariates, 1)

        return treated_outcome_all, treated_outcome, treated_covariates
    

    def _process_control_data(self, dataset, outcome_var, id_var, time_var, treatment_period, treated_unit, n_controls, 
                            periods_all, periods_pre_treatment, covariates):
        '''
        Extracts 
        '''

        #Every unit that is not the treated unit is control
        control_data_all = dataset[dataset[id_var] != treated_unit]
        control_outcome_all = np.array(control_data_all[outcome_var]).reshape(n_controls, periods_all).T #All outcomes
        
        #Only pre-treatment
        control_data = control_data_all[dataset[time_var] < treatment_period]
        #Extract outcome, then shape as matrix
        control_outcome = np.array(control_data[outcome_var]).reshape(n_controls, periods_pre_treatment).T
        
        #Extract the covariates for all the control units
        #Identify which rows correspond to which control unit by setting index, 
        #then take the unitwise mean of each covariate
        #This results in the desired (n_control x n_covariates) matrix
        control_covariates = np.array(control_data[covariates].\
                set_index(np.arange(len(control_data[covariates])) // periods_pre_treatment).mean(level=0)).T

        return control_outcome_all, control_outcome, control_covariates

    def transform_data(self):
        '''
        Takes an appropriately formatted, unprocessed dataset
        returns dataset with changes computed for the outcome variable
        Ready to fit a Difference-in-Differences Synthetic Control

        Transformation method - MeanSubtraction: 
        Subtracting the mean of the corresponding variable and unit from every observation
        '''
        mean_subtract_cols = self.dataset.groupby(self.id).apply(lambda x: x - np.mean(x)).drop(columns=[self.time], axis=1)
        return pd.concat([data[["ID", "Time"]], mean_subtract_cols], axis=1)