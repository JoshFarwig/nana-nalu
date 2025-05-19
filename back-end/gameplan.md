### must have features  

- [ ] Users register / create accounts 
- [ ] Authentication / Authorization for single user type 
- [ ] Users can view a map 
- [ ] Users can view the current registered bouys / their locations 
- [ ] Users can create a surf spot  
- [ ] Users can view their current registered surf spots 
- [ ] Users can create logs (notes) on the surf spot


### cool but, am i becoming the idea man? 

- [ ] Surf spots can snapshot days when its good a  
- [ ] Users can specify some general parameters (swht, sw, wdspd) for when a surf spot is "fair" or "good"   
- [ ] Implement a simple yet complex for me lol approach to wave refracting 
    - [ ] Shadow / line of sight approach for a first implementation


### data, models, database structure and ideas  

*database entities* 

Need to have a users entity to tie spots to 

Need to allow users to make surf spots which primarily indicate a point 

Surf spots can have 

"surf spots" 


### algorithms / thinktanks 
 
*Bouy data calculations / surf spot score calculations* 

- Creating some kind of single "score" for each surf spot a user registers? 
- Score bases on a variety of values, considering swdr, swht, island locations, wave refactoring 
    and locations of bouy + surf spot. 
- Some kind of data plot for each bouy? Each bouy then has a base score for that spot?  
- Spot must consider the surrounding islands, wave inflections, and bouy spots?  
- Then based on some of those factors, score or even maybe average a weight for each bouy? then based on the average takes a combination of both bouy's data? Prioritizing the one that has the better direction angle for the spot? 
- Is this an application for deep learning? or a GIS approach? Do I need to map out the area of the islands to simulate waves? This is probably overengineering for now, should just have spots find bouy data depending on the distance between spot and bouy data, 
- start simple

*todos*
- [ ]
- [ ] 
- [ ]



### testing options and philosophy