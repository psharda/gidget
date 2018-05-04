#!/bin/bash
#SBATCH --job-name fmc38
#SBATCH -n 120
#SBATCH -t 2-00:00
#SBATCH -p shared
#SBATCH --mem-per-cpu=10000
#SBATCH --mail-type=ALL
#SBATCH --mail-user=johncforbes@gmail.com

module unload python/2.7.6-fasrc01

module load python/2.7.13-fasrc01

cd $GIDGETDIR/py
mpirun -n 120 python broad_svm.py > estd.${SLURM_JOB_ID}.out 

