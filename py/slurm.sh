#!/bin/bash
#SBATCH --job-name fmc18
#SBATCH -n 128 
#SBATCH -t 4-00:00
#SBATCH -p general
#SBATCH --mem-per-cpu=3500
#SBATCH --mail-type=ALL
#SBATCH --mail-user=johncforbes@gmail.com

module load python/2.7.13-fasrc01

mpirun -n 128 python broad_svm.py > estd.${SLURM_JOB_ID}.out 

