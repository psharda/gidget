#include <vector>
#include <string>
#include <math.h>

#include <gsl/gsl_spline.h>
#include <gsl/gsl_vector.h>

#include "StellarPop.h"

class Cosmology;
class Dimensions;
struct RafikovQParams;
struct Initializer;
class FixedMesh;
class Debug;
class AccretionHistory;


// Main container for the physical quantities which make up the disk.
// Basic structure is a set of arrays of nx elements (indexed from 1).
class DiskContents {
 public:
  DiskContents(double tH,double eta,
               double sigth,double epsff,
	           double ql,double tol,
               bool aq, double mlf,
               double mlfColScal, double mlfFgScal,
               double mlfMhScal,
               Cosmology&,Dimensions&,
               FixedMesh&,Debug&,
    	       double thk,bool migratePassive,
               double Qinit, double km,
	           unsigned int NA, unsigned int NP,
	           double minSigSt, 
               double rfrec, double zetarec,
    	       double fh2min, double tdeph2sc,
               double yrec,
               double ksupp, double kpow,
               double mq, double muq, 
               double ZMx, double enInjFac, 
               double chr, double ahr);

  // Destructor. Cleans up a bunch of memory allocated by the constructor
  // to speed up GSL-related activities (inverting the matrix to solve for
  // the torque, interpolating state variables to compute Y).
  ~DiskContents();

  // Sum up a quantity over the entire disk, weighting 
  // by the area of each annulus
  double TotalWeightedByArea(const std::vector<double>&);

  // Fill in a RafikovQParams struct with the parameters needed to calculate
  // Q at cell n.
  void ComputeRafikovQParams(RafikovQParams*,unsigned int n);

  // Simultaneously adjust sigma and sigma_* (keeping their ratio fixed) until
  // Q is exactly its pre-adjudicated fixed value, fixedQ, at every cell 
  // in the disk.
  void EnforceFixedQ(bool fixedPhi0, bool EnforceWhenQgtrQf);

  // Fill in vectors of the partial derivatives of Q wrt 
  // each state variable
  void ComputePartials();

  void UpdateStTorqueCoeffs( std::vector<double>& UUst, std::vector<double>& DDst, std::vector<double>& LLst, std::vector<double>& FFst);
  void UpdateCoeffs(double redshift,std::vector<double>& UU, std::vector<double>& DD,
		    std::vector<double>& LL, std::vector<double>& FF,
		    double ** tauvecStar,std::vector<double>& MdotiPlusHalfStar,
		    double ** tauvecMRI, std::vector<double>& MdotiPlusHalfMRI,
            std::vector<double>& accProf, double AccRate,
            std::vector<std::vector<int> >& flagList);

  // Diffuse metals in such a way that the total mass in 
  // metals is conserved. 
  void DiffuseMetals(double dt, int species);

  double activeColSt(unsigned int n);
  double activeSigStR(unsigned int n);
  double activeSigStZ(unsigned int n);
  double ComputeQst(unsigned int n);
  // void TridiagonalWrapper(unsigned int,unsigned int);
  void ComputeGItorque(double**,const double,const double,std::vector<double>& UU,std::vector<double>& DD, 
          std::vector<double>& LL, std::vector<double>& FF, std::vector<double>& MdotiPlusHalf);
//  void TauPrimeFromTau(double**);

  // Compute the H2 fraction given a value of chi, column density, and metallicity.
  // This is one part of the approximation in Krumholz (2013). Most of the algorithm is
  // implemented in ComputeColSFR.
  double ComputeH2Fraction(double ch, double thisCol, double thisZ);

  void ZeroDuDt();
  void UpdateRotationCurve(double Mh, double z, double dt);

  // the scale height of the stellar disk in cm
  double hStars(unsigned int n); 
  double hGas(unsigned int n); 

  // Find the density in g/cc from stars + dark matter
  double ComputeRhoSD(unsigned int n);

  // Compute the star formation rate in every cell
  double ComputeColSFR(double Mh, double z);
  double ComputeColSFRapprox(double Mh, double z);

  // Compute the loss in column density experienced by 
  // cell n due to outflows. (Simple mass loading factor 
  // prescription)
  void ComputeMassLoadingFactor(double Mh, std::vector<double>& colst);

  // Compute the time rate of change of the velocity 
  // dispersion of stellar population sp.
  double dSigStRdt(unsigned int n, unsigned int sp, 
		   std::vector<StellarPop*>&, double ** tauvecStar,std::vector<double>& MdotiPlusHalfStar);
  double dSigStZdt(unsigned int n, unsigned int sp, 
		   std::vector<StellarPop*>&, double ** tauvecStar,std::vector<double>& MdotiPlusHalfStar);

  // Append the properties of each StellarPop in the 
  // given vector to an output file.
  void WriteOutStarsFile(std::string filename, 
			 std::vector<StellarPop*>&,
			 unsigned int,unsigned int step);

  // Append the radially-dependent properties of the disk to an output file, 
  // and the purely time dependent properties to a different file
  void WriteOutStepFile(std::string filename,AccretionHistory & acc, 
                        double t, double z, double dt, 
                        unsigned int step,double **tauvec,double **tauvecStar,double ** tauvecMRI,
                        std::vector<double>& MdotiPlusHalf,std::vector<double>& MdotiPlusHalfMRI,
                        std::vector<double>& accProf, double fAccInner);

  // A few self-explanatory functions...
  double GetDlnx() {return dlnx;};
  double GetMinSigSt() { return minsigst; };
  double GetRfRECinst() {return RfRECinst; };
  double GetRfRECasym() {return RfRECasym; };
  std::vector<double>& GetX() {return x;};
  std::vector<double>& GetUu() { return uu;};
  std::vector<double>& GetBeta() {return beta;};
  std::vector<double>& GetSig() { return sig;};
  std::vector<double>& GetCol() { return col;};
  std::vector<double>& GetColSFR() { return colSFR;}
  std::vector<StellarPop*>& active() { return spsActive;}
  std::vector<StellarPop*>& passive() { return spsPassive;}
  //std::vector<double>& GetYy() {return yy;}
  Dimensions& GetDim() { return dim;}
  Cosmology& GetCos() { return cos;}
  FixedMesh& GetMesh() { return mesh;}
  Debug& GetDbg() { return dbg;}

  // Compute the time derivatives of all state variables 
  // at all radii.
  void ComputeDerivs(double **tauvec,std::vector<double>& MdotiPlusHalf,
                  double ** tauvecMRI,std::vector<double>& MdotiPlusHalfMRI,
                  std::vector<double>& accProf, double AccRate,
                  std::vector<std::vector<int> >& flagList);

  // Given the state variables and their derivatives, 
  // compute a time step such that no quantity is 
  // changing too quickly. The pointers record which
  // variable and which cell is limiting the time step.
  double ComputeTimeStep(const double z,int*,int*,double **,std::vector<double>& MdotiPlusHalfStar);

  // Given a time step, state variables, and their time 
  // derivatives, do a forward Euler step
  void UpdateStateVars(const double dt, const double dtPrev, 
		       const double redshift,double **tauvec,double AccRate,
                       double **tauvecStar,
		       std::vector<double>& MdotiPlusHalf,
		       std::vector<double>& MdotiPlusHalfStar,
		       std::vector<double>& MdotiPlusHalfMRI,
               double fracAccInner, double stAcc);

  // Using parameters which specify the initial conditions, 
  // fill in the initial values for the state variables
  // and fixed quantities (x, beta, u,... )
  // This method assumes constant ratios sigst/sig, colst/col 
  // as functions of radius (i.e. constant fg and constant phi)
  void Initialize(double phi0,double fg0);

  // Similar to the above, except put in an exponential scale 
  // length and constant velocity dispersion for the stars
  void Initialize(double fcool, double fg0,
		  double sigst0, double Mh0, double MhZs,
		  double stScaleLength);

  void Initialize(double fcool, double fg0,
                  double sig0, double tempRatio, double Mh0,
                  double MhZs, double stScaleLength, double zs,
                  const double stScaleReduction, const double gaScaleReduction,
                  const double fg0mult, const double ZIGMfac, const double chiZslope, const double deltaBeta, const double ZIGMFe0, const double ZIGMO0);

  // Is one of the current stellar populations 'currently forming'
  //, i.e. since stars are binned by age, is the age of stars 
  // formed at the current time step such that they will belong 
  // to an existing stellar population, or does a new one need to 
  // be created? In the latter case, create a new population.  The 
  // switch 'active' lets the method know whether we're dealing 
  // with the active or the passive stellar population. In the 
  // former case, the new stellar population, if it's created, 
  // will be taken from an older population. In the latter case, 
  // the new stellar population will be just the stars formed in 
  // this time step.
  void AddNewStellarPop(const double redshift,
                        const double dt,
			std::vector<StellarPop *>&,
			bool active);

    void FormNewStars(StellarPop & currentlyForming, double dt, double redshift);

  // Fill tauvec with the torque and its first derivative, i.e. 
  // solve the torque equation given an inner and outer boundary 
  // condition. These are such that tau(x=xmin)=IBC and tau'(x=1)=OBC
/*   void ComputeTorques(double **tauvec,  */
/* 		      const double IBC,  */
/* 		      const double OBC); */

  // Do the same thing as ComputeTorques, except instead of 
  // solving the torque equation which enforces dQ/dt=0, this 
  // equation just computes the torques for a given alpha viscosity.
  // Also, if the torque as computed here is larger than that 
  // computed by ComputeTorques, replace tau and tau' with 
  // the values computed here. The idea is that if GI shuts down
  // and MRI still operates, let the gas be transported by MRI.
  void ComputeMRItorque(double **tauvec, const double alphaMRI);

  // Store enough information to initialize a simulation in 
  // the Initializer object in.
  void store(Initializer& in);

  // Given the information stored in the Initializer object, 
  // initialize the simulation
  void Initialize(Initializer& in, bool fixedPhi0);


 private:
  std::vector<double> col,sig; // gas column density and velocity dispersion
  std::vector<double> dQdS,dQds; // partial derivatives dQ/dS and dQ/ds
  std::vector<double> dQdu,dudt; // necessary for computing the forcing term coming from a changing rotation curve
  std::vector<double> dQdSerr,dQdserr; //.. and their errors
  std::vector<double> dcoldt,dsigdt,dZDiskFedt, dZDiskOdt,colSFR; // time derivatives
  std::vector<double> mBubble,ColOutflows, MassLoadingFactor;
  std::vector<double> dSdtMig;
  std::vector<double> dZDiskOdtDiff, dZDiskOdtAdv; // components of the metallicity time derivative
  std::vector<double> dZDiskFedtDiff, dZDiskFedtAdv; // components of the metallicity time derivative
  std::vector<double> dMZOdt, MZO;
  std::vector<double> dMZFedt, MZFe;
//  std::vector<double> colZ, dcolZdt;
  std::vector<double> dcoldtIncoming, dcoldtOutgoing; // mass balances in a single cell (dimensionless!)
  std::vector<double> dcoldtPrev,dsigdtPrev,dZDiskFedtPrev, dZDiskOdtPrev; // time derivatives at the previous timestep.
//  std::vector<double> MdotiPlusHalf;
//  std::vector<double> MstarDotIPlusHalf;

  std::vector<double> colvPhiDisk, colstvPhiDisk; // used to store the actual column density distributions used to calculated vPhiDisk. These are the regular column density distributions (col and activeColSt()) passed through a discrete fourier transform and with their high-k components exponentially suppressed.
  std::vector<double> dsigdtTrans, dsigdtDdx, dsigdtHeat, dsigdtCool, dsigdtSN, dsigdtAccr;

  // store the cells where we have turned off forcing in the
  // torque equation.
  std::vector<int> keepTorqueOff;

  // store (dS/dt)*dt from artificial diffusion (not currently used)
  std::vector<double> diffused_dcoldt;

  // store the metal fluxes for metal diffusion, defined as the
  // net flux of metal mass from bin n+1 to bin n
//  std::vector<double> ZFlux;

  // a vector of stellar populations which affect the gravitational 
  // dynamics of the disk
  std::vector<StellarPop*> spsActive; 
  // stellar populations which evolve passively, i.e. do not 
  // affect the gas dynamics.
  std::vector<StellarPop*> spsPassive; 
  
  std::vector<double> ZDiskO, ZDiskFe; // metallicity at each cell
  unsigned int nx; // number of cells

  unsigned int ksuppress; // k at which to begin exponentially suppressing modes to caclulate vPhiDisk
  double kpower; // power to raise argument of the exponential in the above suppression.
  
  //  Dimensionless values of:
  std::vector<double> &
    x,     // position of each cell
    beta,  // power law index of rotation curve
    uu,    // local circular velocity
    uDisk,
    uDM,
    uBulge,
//    yy,    // inward velocity of stars
    betap; //d(beta)/dx 

  std::vector<double> fH2, G0, dampingFactors; // arrays solved during ComputeColSFR(): the H2 fraction by mass and the radiation field in solar neighborhood units
  
  
//  std::vector<double>
//    LL,UU,DD,FF; // coefficients of the torque equation


  // inner truncation radius, logarithmic width of a cell,
  // and factor by which to reduce the timestep TOL
  const double XMIN, dlnx,TOL; 

  Dimensions& dim; // store dimensional quantities
  Cosmology& cos; // store cosmology
  FixedMesh& mesh;
  Debug& dbg;

  const bool migratePassive;

  // Physical parameters of the simulation:
  const double 
    // timescale in local orbital times for Q_* to approach Q_lim
    tauHeat, 

    // dissipation rate parameter - how much of the gas's 
    // non-thermal kinetic energy Sigma sigma_nt^2 is 
    // dissipated in a scale height crossing time? 
    // eta=1.5 corresponds to all KE per crossing time
    ETA, 
    sigth, // dimensionless thermal velocity dispersion (set by T_gas)
    EPS_ff, // star formation efficiency per free fall time
    Qlim, // Q below which transient spirals heat the stellar disk
    thickness, // correction to Q owing to finite thickness
    constMassLoadingFactor, 
    mlfColScaling,
    mlfFgScaling,
    mlfMhScaling,
    MQuench,
    muQuench,

    tDepH2SC,
    fH2Min,

    // the value of Q which we fix at the beginning of the simulation.
    // Reasonable values are between 1 and 2 or so, depending on the
    // thickness correction used (if any). See Elmegreen (2011) for
    // details on why one should probably choose a number >1.
    fixedQ,

    CloudHeatingRate,
    AccretionHeatingRate; 


  // the minimum sig_st = minsigst
  double minsigst;

  // properties of the "bulge", i.e. the region inside the inner
  // truncation radius of the disk
  double ZBulgeFe,ZBulgeO,MBulge;

  double MHalo;

  // parameters controlling the instantaneous recycling approx.
  // RfREC is split into inst (instantaneous) and asymptotic (asym).
  //  the former is the short-term remnant fraction. This is arbitrary/for numerical reasons < 1. For
  //  a truly non-instantaneous recycling process, we'd just set this to 1 and let the stellar population
  //  return material as needs be.
  //  asym is the long-term remnant fraction - how much remains after a long (cosmological) timescale.
  double yRECFe, yRECO, RfRECinst, RfRECasym, xiREC; 
  
  double Z_IGMFe, Z_IGMO; // absolute units

  bool analyticQ;  // use analytic (Romeo-Wiegert 2011) or numerical (Rafikov 2001) Q
  std::vector<double> CumulativeSF; // Total number of cells ever formed in each cell
  std::vector<double> CumulativeTorqueErr2; // Cumulative error in the torque equation..
  std::vector<double> CumulativeTorqueErr;  // measured in various ways
  std::vector<double> d2taudx2;             // tau''
  std::vector<double> CuStarsOut, CuGasOut; // Cumulative stars or gas which leave a cell due to migration
  double initialStellarMass, initialGasMass; // initial total masses in stars and gas
  double cumulativeMassAccreted;             // total mass accreted at the outer edge fo the disk
  double cumulativeStarFormationMass;        // total mass of stars ever formed
  double cumulativeGasMassThroughIB;         // total mass of gas which ever flows through the inner boundary
  double cumulativeStellarMassThroughIB;     // total mass of stars which flow through the inner boundary
  double CumulativeTorque; // integral of tau(x=1) dt.

  double kappaMetals;

  double * colst_gsl;
  double * sigst_gsl;
  gsl_interp_accel * accel_colst;
  gsl_interp_accel * accel_sigst;
  gsl_spline * spline_colst;
  gsl_spline * spline_sigst;

  gsl_vector *lr, *diag, *ur;
  gsl_vector *tau, *forcing;
  
  const double ZMix; // a number between 0 and 1 controlling the fraction of ejected metals mixed back into the accretion flow.
  const double dd,dm1,dmm1,dmdinv,sqd;

  const double energyInjectionFactor;

  const unsigned int NActive, NPassive;
};

  void ComputeFluxes(double ** tauvec,std::vector<double>& MdotiPlusHalf,FixedMesh & mesh);

    
  double ddxUpstream(std::vector<double>& vec, std::vector<double>& x, std::vector<int>& flags, unsigned int n);
  void ComputeUpstreamFlags(std::vector<int>& flags, std::vector<double>& mdot1, std::vector<double>& mdot2, unsigned int n);
  void ComputeFlagList(std::vector<double>& mdot1, std::vector<double>& mdot2, std::vector<std::vector<int> >& flagList);


