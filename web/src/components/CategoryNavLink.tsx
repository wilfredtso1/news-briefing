import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Growth_chart from './icons/Growth_chart.tsx'
import School_building_with_flag from './icons/School_building_with_flag.tsx'
import Potted_plant_with_leaves from './icons/Potted_plant_with_leaves.tsx'


    
// Component

        function CategoryNavLink({
            variant,
            label
        }: {
            variant: "work" | "school" | "life";
            label: string;
        }) {
            let IconComponent: JSX.Element;

            if (variant === "work") {
                IconComponent = <Growth_chart />;
            } else if (variant === "school") {
                IconComponent = <School_building_with_flag />;
            } else {
                IconComponent = <Potted_plant_with_leaves />;
            }

            return (
                <a className={"pageNav_pageNavLink__zAxT7"}>
                    <span className={"TemplateGallerySubNavigationWithCategories_categoryButton__fluQ1"}>
                        {IconComponent}
                        <span>
                            {label}
                        </span>
                    </span>
                </a>
            );
        }
    

export default CategoryNavLink
