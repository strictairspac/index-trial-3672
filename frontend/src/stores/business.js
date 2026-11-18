import {workloads,candidates,experiments,stress} from '../api/business.js';
export const store={workloads:[],candidates:[],experiments:[],stress:[],user:null};
export async function refresh(){[store.workloads,store.candidates,store.experiments,store.stress]=await Promise.all([workloads.list(),candidates.list(),experiments.list(),stress.list()]);}
