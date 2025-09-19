## phase and feature breakdowns 
### p1 must have mini features 

- [ ] Users register / create accounts 
- [ ] Authentication / Authorization for single user type, but maybe build out normal, pro, admin types. 
- [ ] Users can view a map interface. Look into free map options or even creating your own base map (as long as thats not too out of scope)
- [ ] Users can view the current registered bouys / their surf spots
- [ ] Users can create a surf spot (Build out the spots in the database with the feature in mind that users can share spots or invite others to a spot / or combine the two)
- [ ] Users can view their current registered surf spots 
- [ ] Users can create logs (notes) on the surf spot 


### p2 must haves  
- [ ] Implement a simple yet complex for me lol approach to wave refraction
    - [ ] Shadow / line of sight approach for a first implementation  
- [ ] Users can set "parameters" for when a spot is actually good   
- [ ] Build out the back-end caching system for each registered bouy. make sure in p1 to build out a bouy registry, this will make sure that any new bouy will get a TTL redis cache setup.    
- [ ] Look into building out your own base map for the islands of hawaii and their bouys. 

### p3 must haves 

- [ ] todo 
- [ ] todo 
- [ ] todo

#### notes on features or phases 

> *surf_spots* 

need to consider how a spot chooses how many, or what kind of combination of bouy data it takes depending on the location of where the bouy is entered. that or it does a combination of all bouys to make an approximation on the wave conditions, this could be too expensive to do even with caching.  

also, what if a user registers a spot inland? do I need to make a base-map of the islands so that users can only make a spot that is on the shore-line? is this wayyy out of scope? 

need to consider what the approaches are for setting up better prediction models for waves and mapping approaches 

probably best to start off with open-source options on the front-end where I can if I want to in the future develop my own base maps of the islands w/ shapefiles.

> *setting parameters for users to tell when a spot is good*

(the shadow / los approach will give a generate outline of the actual conditions, but it may not be spot on, so ideally either have users specific a range when its good)  

also, get some feedback from users on this, maybe users want to specific multiple combos of params? for example, tavares. tavares is a super variable spot since of the outer reef, and typically its good when theres enough swell / tide to get over the outer reef.  

tldr, tavares can be good during mid-tide but enough swell, or really good when its high-tide high swell. different spots will also have different wind readings

### cool but, am i becoming the idea man? 

- [ ] Building out a tide / wind integration into spots? Would I also need my los / shadow model to have factors like wind and tide in consideration? also how much processing power will a model like this take?

## thinking about forms of data  

### database entities  

4 primary ones are user, bouy, surf_spot, and observation. 

#### user  

should include basic user profile data i.e.  
- id 
- email 
- password (hashed) 
- first_name 
- last_name 
- friends []

#### bouy   
- id  
- station_id (refers to NOAA id, this could just be the pk, look into pros and cons) 
- lat 
- long  
- type (enum, wave, tide / wind, combo?)
- ... any other meta-data needed or parameters needed when using NOAA's https server for nbdc 

#### surf_spot  
- id  
- lat 
- long  
- ... the combined predicted bouy data for the spot, calculated by some service layer biz logic. 
- users [] (multipe users can "share" a spot, they can add observations to the same spot as well)
- bouys [] (not too sure how this is gonna work for now, but depending on the spots location, a cominbation of bouys will be shown. a certain weight of their data will be applied basic on wave-refaction and other models.)
- observations [] (takes a snapshot of the conditions of the surf_spot of that day, allows users to add some general notes about the spot)

#### observation
- id (this may not be needed)
- surf_spot_id (these pretty much make the pk)
- user_id (these pretty much make the pk) 
- ... all relevant data from the bouy
- note (limit to a certain amount of chars) 

### database /init/ or scripts

#### schemas 

should create some organized schemas for the more privatizied data geared towards home-brew surf forecast generation

#### role management? 

if this app scales a fair amount, could be important to start incorperating some roles (i.e. app_user to create role that only api uses, or maybe read_only role) 

#### seeding 

potientally start setting up seeding for integration testing? or just unit testing.

## biz logic and potiental approaches

### algorithms / thinktanks 
 
*Bouy data calculations / surf spot score calculations* 

Creating some kind of scoring system to rank what weight each bouy should have in terms of combining data for a surf spot? This would need to take into account the direction and distance of the bouy from the spot in the most naive approach.

Should the score base on a variety of values, considering swdr, swht, island locations, wave refactoring and locations of bouy + surf spot? 

Spots at some point must consider the surrounding islands / its own spot, wave inflections, and bouy locations? Then based on some of those factors, score or even maybe average a weight for each bouy? then based on the average takes a combination of both bouy's data? Prioritizing the one that has the better direction angle for the spot? This may even require its own base map of the island via shapefile. PostGIS may be needed in this case.

> 📗 **look into gh examples of open sourced wave modeling**

**START SIMPLE**, have surf spots just choose a bouy based on their distance from the spot, then it displays that bouys data. Then move towards more complex modeling and base map creations

### testing options / philosophies